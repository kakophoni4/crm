<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NPopover,
  NSpace,
  NSpin,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { format } from 'date-fns'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { leadCommentItems } from '@/features/leads/comments'

import type {
  Contact,
  ContactActivityItem,
  ContactCrmSummary,
  GroupOwnershipItem,
} from '@/entities/contact/types'
import type { LeadListItem } from '@/features/leads/types'
import { ensureBotDirectory } from '@/features/bots/directory'
import { listContactLeads } from '@/features/leads/api'
import {
  formatCrmSummaryBadge,
  formatLeadBotLabel,
  formatLeadDate,
  formatLeadOpenState,
  leadListItemLabel,
} from '@/features/leads/mapping'
import ContactOwnerBadge from '@/entities/contact/ContactOwnerBadge.vue'
import { contactStatusLabel } from '@/entities/contact/types'
import { useChatsStore } from '@/features/chats/store'
import {
  getContact,
  getContactHistory,
  updateContact,
} from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const props = defineProps<{
  id: number
}>()

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const contact = ref<Contact | null>(null)

const form = ref({
  note: '',
  phone: '',
  email: '',
  telegram_username: '',
})

const markIlliquid = ref(false)

const historyItems = ref<ContactActivityItem[]>([])
const historyLoading = ref(false)
const activeTab = ref('main')
const historyLoaded = ref(false)

const leadsItems = ref<LeadListItem[]>([])
const leadsLoading = ref(false)
const leadsLoaded = ref(false)

const crmSummaryBadge = computed(() =>
  formatCrmSummaryBadge(contact.value?.crm_summary as ContactCrmSummary | undefined),
)

function openLeadInChats(row: LeadListItem): void {
  if (row.chat_id == null) return
  void router.push({
    name: 'chats',
    query: { chatId: String(row.chat_id), leadId: String(row.id) },
  })
}

function renderLeadComments(row: LeadListItem) {
  const items = leadCommentItems(row)
  if (!items.length) {
    return '—'
  }
  const sorted = [...items].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
  const latest = sorted[sorted.length - 1]
  if (!latest) {
    return '—'
  }
  if (sorted.length === 1) {
    return h('div', { class: 'contact-lead-comment', onClick: (e: Event) => e.stopPropagation() }, [
      h('div', { class: 'contact-lead-comment__text' }, latest.body),
      h('div', { class: 'contact-lead-comment__time' }, formatDate(latest.created_at)),
    ])
  }
  return h(
    NPopover,
    {
      trigger: 'click',
      placement: 'left',
      onClick: (e: Event) => e.stopPropagation(),
    },
    {
      trigger: () =>
        h('div', { class: 'contact-lead-comment contact-lead-comment--link', onClick: (e: Event) => e.stopPropagation() }, [
          h('div', { class: 'contact-lead-comment__text' }, latest.body),
          h('div', { class: 'contact-lead-comment__time' }, `Ещё ${sorted.length - 1} · ${formatDate(latest.created_at)}`),
        ]),
      default: () =>
        h(
          'ul',
          { class: 'contact-lead-comment__list' },
          sorted.map((item) =>
            h('li', { key: item.id, class: 'contact-lead-comment__item' }, [
              h('div', { class: 'contact-lead-comment__text' }, item.body),
              h('div', { class: 'contact-lead-comment__time' }, formatDate(item.created_at)),
            ]),
          ),
        ),
    },
  )
}

const leadsColumns: DataTableColumns<LeadListItem> = [
  {
    title: 'Дата',
    key: 'created_at',
    width: 150,
    render: (row) => formatLeadDate(row.created_at),
  },
  {
    title: 'Статус',
    key: 'status_label',
    width: 120,
    render: (row) => leadListItemLabel(row),
  },
  {
    title: 'Бот',
    key: 'bot_id',
    width: 140,
    render: (row) => formatLeadBotLabel(row),
  },
  {
    title: 'Открыт/закрыт',
    key: 'closed_at',
    width: 110,
    render: (row) => formatLeadOpenState(row.closed_at),
  },
  {
    title: 'Комментарий',
    key: 'comments',
    minWidth: 220,
    render: (row) => renderLeadComments(row),
  },
  {
    title: '',
    key: 'actions',
    width: 100,
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          quaternary: true,
          disabled: row.chat_id == null,
          onClick: () => openLeadInChats(row),
        },
        { default: () => 'Открыть' },
      ),
  },
]

const canViewHistoryActor = computed(() => auth.canViewHistoryActor)
const showContactPrivateFields = canViewHistoryActor

const showTelegramUserId = computed(() => auth.isAdmin)
const groupOwnership = computed<GroupOwnershipItem[]>(
  () => contact.value?.group_ownership ?? [],
)

const historyTableKey = computed(() =>
  canViewHistoryActor.value ? 'history-with-actor' : 'history-basic',
)

const historyColumns = computed<DataTableColumns<ContactActivityItem>>(() => {
  const cols: DataTableColumns<ContactActivityItem> = [
    {
      title: 'Действие',
      key: 'label',
      minWidth: 260,
      ellipsis: { tooltip: true },
    },
  ]
  if (canViewHistoryActor.value) {
    cols.push({
      title: 'Кто',
      key: 'actor_name',
      width: 180,
      ellipsis: { tooltip: true },
      render: (row) => row.actor_name?.trim() || '—',
    })
  }
  cols.push({
    title: 'Когда',
    key: 'occurred_at',
    width: 168,
    render: (row) => formatDate(row.occurred_at),
  })
  return cols
})

const historyScrollX = computed(() =>
  canViewHistoryActor.value ? 720 : 520,
)

function formatDate(iso: string): string {
  try {
    return format(new Date(iso), 'dd.MM.yyyy HH:mm:ss')
  } catch {
    return iso
  }
}

function syncFormFromContact(c: Contact): void {
  form.value = {
    note: c.note?.trim() ?? '',
    phone: c.phone ?? '',
    email: c.email ?? '',
    telegram_username: c.telegram_username ?? '',
  }
  markIlliquid.value = c.status === 'disabled'
}

async function loadContact(): Promise<void> {
  loading.value = true
  try {
    contact.value = await getContact(props.id)
    syncFormFromContact(contact.value)
    if (contact.value.group_ownership?.length) {
      useChatsStore().setContactOwnership(props.id, contact.value.group_ownership)
    }
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Контакт не найден'
    message.error(text)
    await router.push({ name: 'contacts' })
  } finally {
    loading.value = false
  }
}

async function saveContact(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      note: form.value.note.trim() || null,
    } as Parameters<typeof updateContact>[1]

    if (markIlliquid.value) {
      payload.status = 'disabled'
    } else if (contact.value?.status === 'disabled') {
      payload.status = 'new'
    }

    if (showContactPrivateFields.value) {
      payload.phone = form.value.phone.trim() || null
      payload.email = form.value.email.trim() || null
      payload.telegram_username = form.value.telegram_username.trim() || null
    }

    contact.value = await updateContact(props.id, payload)
    syncFormFromContact(contact.value)
    message.success('Сохранено')
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось сохранить'
    message.error(text)
  } finally {
    saving.value = false
  }
}

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  try {
    const data = await getContactHistory(props.id)
    historyItems.value = data.items
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить историю'
    message.error(text)
  } finally {
    historyLoading.value = false
  }
}

async function loadLeads(): Promise<void> {
  leadsLoading.value = true
  try {
    await ensureBotDirectory()
    const data = await listContactLeads(props.id, { limit: 50 })
    leadsItems.value = data.items
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить сделки'
    message.error(text)
  } finally {
    leadsLoading.value = false
  }
}

onMounted(() => {
  void loadContact()
})

watch(
  () => props.id,
  () => {
    historyLoaded.value = false
    leadsLoaded.value = false
    void loadContact()
  },
)

watch(activeTab, (tab) => {
  if (tab === 'history' && !historyLoaded.value) {
    historyLoaded.value = true
    void loadHistory()
  }
  if (tab === 'leads') {
    leadsLoaded.value = true
    void loadLeads()
  }
})

watch(
  () => auth.user?.role,
  (role, prev) => {
    if (role != null && role !== prev && activeTab.value === 'history') {
      void loadHistory()
    }
  },
)
</script>

<template>
  <section class="contact-detail">
    <NSpace align="center" class="contact-detail__toolbar">
      <NButton quaternary @click="router.push({ name: 'contacts' })">← К списку</NButton>
      <h1 class="contact-detail__title">
        {{ contact?.full_name ?? `Контакт #${id}` }}
      </h1>
      <NTag v-if="crmSummaryBadge" type="info" size="small" round>
        {{ crmSummaryBadge }}
      </NTag>
    </NSpace>

    <NSpin :show="loading">
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane name="main" tab="Карточка">
          <div v-if="groupOwnership.length" class="contact-detail__ownership">
            <h3>Владение по группам</h3>
            <div
              v-for="row in groupOwnership"
              :key="row.group_id"
              class="contact-detail__ownership-row"
            >
              <span>{{ row.group_name }}</span>
              <ContactOwnerBadge
                :owner-full-name="row.owner_full_name"
                :owner-user-id="row.owner_user_id"
                :escalated="Boolean(row.escalated_at)"
                :pending="Boolean(row.pending_inbound_at)"
              />
            </div>
          </div>
          <NForm label-placement="top" class="contact-detail__form">
            <NFormItem label="Имя из Telegram">
              <NInput :value="contact?.full_name ?? ''" disabled />
            </NFormItem>
            <NFormItem label="Пометка">
              <NInput
                v-model:value="form.note"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :disabled="saving"
              />
            </NFormItem>
            <template v-if="showContactPrivateFields">
              <NFormItem label="Телефон">
                <NInput v-model:value="form.phone" :disabled="saving" />
              </NFormItem>
              <NFormItem label="Email">
                <NInput v-model:value="form.email" :disabled="saving" />
              </NFormItem>
              <NFormItem label="Telegram username">
                <NInput v-model:value="form.telegram_username" :disabled="saving" />
              </NFormItem>
            </template>
            <NFormItem v-if="showTelegramUserId && contact?.telegram_user_id != null" label="TG user ID">
              <NInput :value="String(contact.telegram_user_id)" disabled />
            </NFormItem>
            <NFormItem label="Статус клиента">
              <NTag v-if="contact" size="medium" :bordered="false">
                {{ contactStatusLabel(contact.status) }}
              </NTag>
            </NFormItem>
            <NFormItem label="Неликвидный">
              <NSwitch v-model:value="markIlliquid" :disabled="saving" />
            </NFormItem>

            <NSpace>
              <NButton type="primary" :loading="saving" @click="saveContact">Сохранить</NButton>
            </NSpace>
          </NForm>
        </NTabPane>

        <NTabPane name="history" tab="История">
          <NSpin :show="historyLoading">
            <div class="contact-detail__table-wrap contact-detail__table-wrap--history">
              <NDataTable
                :key="historyTableKey"
                :columns="historyColumns"
                :data="historyItems"
                :scroll-x="historyScrollX"
                :row-key="(row: ContactActivityItem) => row.id"
              />
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="leads" tab="Сделки">
          <NSpin :show="leadsLoading">
            <div class="contact-detail__table-wrap contact-detail__table-wrap--leads">
              <NDataTable
                :columns="leadsColumns"
                :data="leadsItems"
                :row-key="(row: LeadListItem) => row.id"
              />
            </div>
          </NSpin>
        </NTabPane>
      </NTabs>
    </NSpin>
  </section>
</template>

<style scoped>
.contact-detail__toolbar {
  margin-bottom: 16px;
}

.contact-detail__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.contact-detail__form {
  max-width: 560px;
}

.contact-detail__ownership {
  margin-bottom: 20px;
  max-width: 560px;
}

.contact-detail__ownership h3 {
  margin: 0 0 8px;
  font-size: 1rem;
}

.contact-detail__ownership-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.contact-detail__table-wrap {
  max-width: 440px;
}

.contact-detail__table-wrap--history {
  max-width: min(100%, 920px);
  width: 100%;
}

.contact-detail__table-wrap :deep(.n-data-table-wrapper) {
  max-width: 100%;
}

.contact-detail__table-wrap--leads {
  max-width: 920px;
}

:deep(.contact-lead-comment__text) {
  white-space: pre-wrap;
  word-break: break-word;
}

:deep(.contact-lead-comment__time) {
  margin-top: 4px;
  font-size: 0.75rem;
  opacity: 0.65;
}

:deep(.contact-lead-comment--link) {
  cursor: pointer;
}

:deep(.contact-lead-comment__list) {
  margin: 0;
  padding: 0;
  list-style: none;
  max-width: 320px;
}

:deep(.contact-lead-comment__item) {
  padding: 8px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

:deep(.contact-lead-comment__item:first-child) {
  border-top: none;
  padding-top: 0;
}

</style>
