<script setup lang="ts">

import {

  NAlert,
  NBadge,

  NButton,

  NEmpty,

  NInput,

  NSelect,

  NSkeleton,

  NSpace,

  NSwitch,

  NSpin,

  NTab,

  NTag,

  NTabs,

  useMessage,

} from 'naive-ui'

import { formatDistanceToNow } from 'date-fns'

import { ru } from 'date-fns/locale'

import { useWindowSize } from '@vueuse/core'
import { ArrowLeft, ChevronDown, MessageSquare } from 'lucide-vue-next'

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'



import type { BotListItem } from '@/entities/bot/types'
import type { ChatListItem, ChatListTab } from '@/entities/chat/types'
import { CHAT_SORT_OPTIONS } from '@/entities/chat/types'
import ContactOwnerBadge from '@/entities/contact/ContactOwnerBadge.vue'
import { listBots } from '@/features/bots/api'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { registerChatListSearchFocus } from '@/features/chats/chat-list-search-focus'
import { useChatsStore } from '@/features/chats/store'
import {
  chatListItemStatusLabel,
  currentLeadIsOpen,
  filterChatWorkflowStatuses,
  filterLeadPipelineStatuses,
  filterOpenLeadPipelineStatuses,
  formatContactClientLabel,
  resolveTerminalStatusId,
} from '@/features/leads/mapping'
import type { StatusOption } from '@/features/leads/types'
import { useStatusesStore } from '@/features/statuses/store'

import TransferCardDialog from '@/features/contacts/transfer-card/TransferCardDialog.vue'
import ChatsNotificationsPane from '@/widgets/chat/ChatsNotificationsPane.vue'

import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import ContactAvatar from '@/shared/ui/ContactAvatar.vue'

import { onChatsInvalidate } from '@/shared/lib/query-invalidation'
import { storage } from '@/shared/lib/storage'

import { connectChatsRealtime } from '@/shared/realtime/chats-ws'
import { connectLeadsRealtime } from '@/shared/realtime/leads-ws'

import { connectOwnershipRealtime } from '@/shared/realtime/ownership-ws'

import MessageInput from '@/widgets/chat/MessageInput.vue'

import MessageList from '@/widgets/chat/MessageList.vue'

import TakeoverBadge from '@/widgets/chat/TakeoverBadge.vue'



const CHATS_NARROW_BREAKPOINT = 1024

const store = useChatsStore()
const auth = useAuthStore()
const route = useRoute()
const { width } = useWindowSize()
const isNarrow = computed(() => width.value < CHATS_NARROW_BREAKPOINT)
const narrowPane = ref<'list' | 'chat'>('list')

const message = useMessage()
const chatListSearchRef = ref<InstanceType<typeof NInput> | null>(null)

const transferCardVisible = ref(false)
const transferInboxOpen = ref(false)
const bots = ref<BotListItem[]>([])
const botsLoading = ref(false)
const pipelineStatuses = ref<StatusOption[]>([])
const openPipelineStatuses = ref<StatusOption[]>([])
const chatWorkflowStatuses = ref<StatusOption[]>([])

const botOptions = computed(() =>
  bots.value.map((bot) => ({ label: bot.name, value: bot.id })),
)

const leadStatusOptions = computed(() =>
  openPipelineStatuses.value.map((row) => ({
    label: row.label,
    value: row.id,
  })),
)

const wonStatusId = computed(() =>
  resolveTerminalStatusId(pipelineStatuses.value, ['won', 'lead_won']),
)
const lostStatusId = computed(() =>
  resolveTerminalStatusId(pipelineStatuses.value, ['lost', 'lead_lost']),
)

const chatWorkflowStatusOptions = computed(() =>
  chatWorkflowStatuses.value.map((row) => ({ label: row.label, value: row.id })),
)

const chatWorkflowLabel = computed(() => store.currentChat?.chat_label?.label?.trim() || null)

const contactClientLabel = computed(() =>
  formatContactClientLabel(store.currentChat?.contact_client_label),
)

const currentLeadStatusId = computed({
  get: () => store.currentChat?.current_lead?.status_id ?? null,
  set: (statusId: number | null) => {
    if (statusId == null) return
    void updateLeadStatus(statusId)
  },
})

const hasOpenLead = computed(() => currentLeadIsOpen(store.currentChat?.current_lead))

const showLeadPipelineSelect = computed(
  () => hasOpenLead.value && leadStatusOptions.value.length > 0,
)

const leadCommentDraft = ref('')
const savingLeadComment = ref(false)

watch(
  () => store.currentChat?.current_lead?.id,
  () => {
    leadCommentDraft.value = ''
  },
)

const showCloseLeadButton = computed(() => hasOpenLead.value)

const showLeadEditor = computed(() => hasOpenLead.value)

const LEAD_PANEL_COLLAPSED_KEY = 'crm.chats.leadPanelCollapsed'
const leadPanelCollapsed = ref(storage.get(LEAD_PANEL_COLLAPSED_KEY) === '1')

const currentLeadStatusLabel = computed(() => {
  const lead = store.currentChat?.current_lead
  if (!lead) return null
  const fromLead = lead.label?.trim()
  if (fromLead) return fromLead
  const match = leadStatusOptions.value.find((row) => row.value === lead.status_id)
  return match?.label ?? null
})

function toggleLeadPanel(): void {
  leadPanelCollapsed.value = !leadPanelCollapsed.value
  storage.set(LEAD_PANEL_COLLAPSED_KEY, leadPanelCollapsed.value ? '1' : '0')
}

const messageScopeTab = computed({
  get: () => store.messageScope,
  set: (value: 'current_lead' | 'all') => {
    void store.setMessageScope(value)
  },
})

const listTabs: { name: ChatListTab; label: string }[] = [

  { name: 'mine', label: 'Мои карточки' },

  { name: 'group', label: 'Вся группа' },

  { name: 'needs_response', label: 'Нужен ответ' },

]



const transferGroupId = computed(() => store.currentChat?.assigned_group_id ?? null)

const canTransferCard = computed(() => {
  const chat = store.currentChat
  const me = auth.user?.id
  if (chat == null || me == null || transferGroupId.value == null) return false
  if (auth.isSenior || auth.isAdmin) return true
  return chat.card_owner_user_id === me
})

const transferGroupName = computed(() => {
  const chat = store.currentChat
  if (chat?.assigned_group_id == null) return null
  return (
    chat.assigned_group_name?.trim() ||
    lookupGroupName(chat.assigned_group_id)?.trim() ||
    null
  )
})

async function onCardTransferred(): Promise<void> {
  await store.fetchList()
  await store.refreshCurrentChatOwner()
}

function isHighlighted(chatId: number): boolean {

  return store.highlightedChatIds.has(chatId)

}



function formatRelative(iso: string | null): string {

  if (!iso) return ''

  try {

    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: ru })

  } catch {

    return ''

  }

}

function chatMetaLine(chat: ChatListItem): string {
  const time = formatRelative(chat.last_message_at)
  const status = chatListItemStatusLabel(chat)
  if (!time) return status ?? ''
  if (!status) return time
  return `${time} · ${status}`
}



async function onSend(text: string, attachments: { file_id: number }[]): Promise<void> {

  try {

    await store.sendMessage(text, attachments)

  } catch (err) {

    const textErr = err instanceof AppError ? err.message : 'Не удалось отправить'

    message.error(textErr)

  }

}



function onTakeoverReleased(): void {

  if (store.currentChatId != null) {

    store.handleTakeoverReleased({ chat_id: store.currentChatId })

  }

}



let stopInvalidate: (() => void) | undefined



async function loadBots(): Promise<void> {
  botsLoading.value = true
  try {
    const data = await listBots()
    bots.value = data.items.filter((bot) => bot.is_active)
  } catch {
    bots.value = []
  } finally {
    botsLoading.value = false
  }
}

const statusesStore = useStatusesStore()

async function loadLeadStatuses(): Promise<void> {
  try {
    const pipelineItems = await statusesStore.fetchByKind('lead_pipeline')
    const allPipeline = filterLeadPipelineStatuses(pipelineItems)
    pipelineStatuses.value = allPipeline
    openPipelineStatuses.value = filterOpenLeadPipelineStatuses(pipelineItems)
  } catch {
    pipelineStatuses.value = []
  }
}

async function loadChatWorkflowStatuses(): Promise<void> {
  try {
    const items = await statusesStore.fetchByKind('chat_label')
    chatWorkflowStatuses.value = filterChatWorkflowStatuses(items)
  } catch {
    chatWorkflowStatuses.value = []
  }
}

async function saveLeadComment(): Promise<void> {
  const lead = store.currentChat?.current_lead
  if (!lead || lead.closed_at != null || savingLeadComment.value) return
  const next = leadCommentDraft.value.trim()
  if (!next) return
  savingLeadComment.value = true
  try {
    await store.updateCurrentLeadComment(next)
    leadCommentDraft.value = ''
    message.success('Комментарий к сделке сохранён')
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось сохранить комментарий'
    message.error(text)
  } finally {
    savingLeadComment.value = false
  }
}

async function updateLeadStatus(statusId: number): Promise<void> {
  try {
    await store.updateCurrentLeadStatus(statusId)
    message.success('Статус сделки обновлён')
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось обновить статус сделки'
    message.error(text)
  }
}

async function onCloseLead(outcomeStatusId: number | null): Promise<void> {
  if (outcomeStatusId == null) return
  try {
    await store.closeCurrentLead(outcomeStatusId)
    message.success('Сделка закрыта')
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось закрыть сделку'
    message.error(text)
  }
}

function openChatFromQuery(): void {
  const raw = route.query.chatId
  const chatId = typeof raw === 'string' ? Number(raw) : NaN
  if (Number.isFinite(chatId) && chatId > 0) {
    void openChatMobile(chatId)
  }
}

function openChatMobile(chatId: number): void {
  void store.openChat(chatId)
  if (isNarrow.value) narrowPane.value = 'chat'
}

function backToChatList(): void {
  narrowPane.value = 'list'
  store.closeChat()
}

watch(isNarrow, (narrow) => {
  if (!narrow) narrowPane.value = 'list'
})

watch(
  () => store.currentChatId,
  (chatId) => {
    if (chatId != null && isNarrow.value) narrowPane.value = 'chat'
  },
)

onMounted(() => {
  registerChatListSearchFocus(() => chatListSearchRef.value?.focus())
  void ensureGroupDirectory()
  void store.fetchList()
  void loadBots()
  void connectChatsRealtime()
  void connectLeadsRealtime()

  void connectOwnershipRealtime()
  void loadLeadStatuses()
  void loadChatWorkflowStatuses()

  stopInvalidate = onChatsInvalidate(() => {
    void store.fetchList()
  })

  openChatFromQuery()
})

watch(
  () => route.query.chatId,
  () => {
    openChatFromQuery()
  },
)

onUnmounted(() => {
  registerChatListSearchFocus(null)
  stopInvalidate?.()
})

</script>



<template>

  <section class="chats-page">

    <header class="chats-page__header">

      <h1 class="chats-page__title">Чаты</h1>

      <NButton
        v-if="isNarrow"
        quaternary
        size="small"
        @click="transferInboxOpen = true"
      >
        Уведомления
      </NButton>

    </header>



    <div
      class="chats-page__split"
      :class="{
        'chats-page__split--narrow': isNarrow,
        'chats-page__split--show-list': isNarrow && narrowPane === 'list',
        'chats-page__split--show-chat': isNarrow && narrowPane === 'chat',
      }"
    >

      <aside class="chats-page__list-pane">

        <NTabs

          v-model:value="store.listTab"

          type="segment"

          size="small"

          class="chats-page__tabs"

        >

          <NTab v-for="tab in listTabs" :key="tab.name" :name="tab.name" :tab="tab.label" />

        </NTabs>



        <NSpace class="chats-page__filters" vertical :size="8">

          <NInput
            ref="chatListSearchRef"
            v-model:value="store.filters.q"
            clearable
            placeholder="Поиск по контакту…"
            aria-label="Поиск в списке чатов"
          />

          <NSelect
            v-model:value="store.filters.chatStatusId"
            :options="chatWorkflowStatusOptions"
            placeholder="Статус чата"
            clearable
          />

          <NSelect
            v-model:value="store.filters.botId"
            :options="botOptions"
            :loading="botsLoading"
            placeholder="Бот"
            clearable
          />

          <label class="chats-page__unread-toggle">
            <span>Только непрочитанные</span>
            <NSwitch v-model:value="store.filters.unreadOnly" size="small" />
          </label>

          <NSelect
            v-model:value="store.filters.leadStatusId"
            :options="leadStatusOptions"
            placeholder="Статус сделки"
            clearable
          />

          <label class="chats-page__unread-toggle">
            <span>Только с открытой сделкой</span>
            <NSwitch v-model:value="store.filters.leadOpenOnly" size="small" />
          </label>

          <NSelect
            v-model:value="store.filters.sort"
            :options="CHAT_SORT_OPTIONS"
            placeholder="Сортировка"
          />
        </NSpace>

        <div v-if="store.listInitialLoading" class="chats-page__skeleton">
          <NSkeleton v-for="n in 6" :key="n" text :repeat="2" style="margin-bottom: 12px" />
        </div>

        <NSpin v-else :show="store.listLoading && store.listLoaded">
          <ul v-if="store.displayListItems.length" class="chats-page__list">
            <li
              v-for="chat in store.displayListItems"

              :key="chat.id"

              class="chats-page__list-item"

              :class="{

                'chats-page__list-item--active': store.currentChatId === chat.id,

                'chats-page__list-item--highlight': isHighlighted(chat.id),

                'chats-page__list-item--needs-response':

                  store.needsResponseChatIds.has(chat.id) || chat.needs_response,

              }"

              @click="openChatMobile(chat.id)"

            >

              <div class="chats-page__list-row">

                <ContactAvatar
                  :contact-id="chat.contact_id"
                  :full-name="chat.contact_name"
                  :size="32"
                />

                <strong class="chats-page__list-name">{{ chat.contact_name }}</strong>

                <NBadge v-if="chat.unread_for_me" dot />

              </div>

              <ContactOwnerBadge

                class="chats-page__owner"

                :owner-full-name="chat.card_owner_full_name"

                :owner-user-id="chat.card_owner_user_id"

                :escalated="Boolean(chat.escalated_at)"

                :pending="Boolean(chat.pending_inbound_at)"

              />

              <p class="chats-page__preview">{{ chat.last_message_preview ?? '—' }}</p>

              <span class="chats-page__meta">{{ chatMetaLine(chat) }}</span>

            </li>

          </ul>

          <NEmpty
            v-else-if="store.listError"
            description="Ошибка загрузки"
          >
            <template #extra>{{ store.listError }}</template>
          </NEmpty>
          <NEmpty v-else description="Нет чатов по фильтрам" />

        </NSpin>

      </aside>



      <main class="chats-page__chat-pane">

        <template v-if="store.currentChat">

          <header class="chats-page__chat-header">

            <div class="chats-page__chat-header-top">

            <div class="chats-page__chat-header-main">

              <NButton
                v-if="isNarrow"
                quaternary
                circle
                class="chats-page__back"
                aria-label="К списку чатов"
                @click="backToChatList"
              >
                <ArrowLeft :size="18" />
              </NButton>

              <ContactAvatar
                :contact-id="store.currentChat.contact_id"
                :full-name="store.currentChat.contact_name"
                :size="40"
              />

              <div class="chats-page__chat-identity">

                <h2>{{ store.currentChat.contact_name }}</h2>

                <div class="chats-page__chat-meta">
                  <ContactOwnerBadge
                    :owner-full-name="store.currentChat.card_owner_full_name"
                    :owner-user-id="store.currentChat.card_owner_user_id"
                    :escalated="Boolean(store.currentChat.escalated_at)"
                    :pending="Boolean(store.currentChat.pending_inbound_at)"
                  />
                  <NTag v-if="chatWorkflowLabel" size="small" :bordered="false">
                    {{ chatWorkflowLabel }}
                  </NTag>
                  <NTag v-if="contactClientLabel" size="small" type="info" :bordered="false">
                    {{ contactClientLabel }}
                  </NTag>
                </div>

              </div>

            </div>

            <NSpace>
              <NButton
                v-if="canTransferCard"
                size="small"
                @click="transferCardVisible = true"
              >
                Передать карточку
              </NButton>
            </NSpace>

            </div>

            <div
              v-if="showLeadEditor"
              class="chats-page__lead-panel"
              :class="{ 'chats-page__lead-panel--collapsed': leadPanelCollapsed }"
            >
              <button
                type="button"
                class="chats-page__lead-panel-toggle"
                :aria-expanded="!leadPanelCollapsed"
                @click="toggleLeadPanel"
              >
                <span class="chats-page__lead-panel-toggle-title">Сделка</span>
                <NTag
                  v-if="currentLeadStatusLabel"
                  size="small"
                  :bordered="false"
                  class="chats-page__lead-panel-toggle-tag"
                >
                  {{ currentLeadStatusLabel }}
                </NTag>
                <ChevronDown
                  class="chats-page__lead-panel-chevron"
                  :class="{ 'chats-page__lead-panel-chevron--collapsed': leadPanelCollapsed }"
                  :size="16"
                />
              </button>

              <div v-show="!leadPanelCollapsed" class="chats-page__lead-panel-body">
              <div class="chats-page__lead-panel-toolbar">
                <div v-if="showLeadPipelineSelect" class="chats-page__lead-field chats-page__lead-field--status">
                  <span class="chats-page__lead-label">Статус сделки</span>
                  <NSelect
                    v-model:value="currentLeadStatusId"
                    class="chats-page__lead-status"
                    size="small"
                    :options="leadStatusOptions"
                    :consistent-menu-width="false"
                    :menu-props="{ class: 'chats-page__status-menu' }"
                    :loading="store.updatingLeadStatus"
                    placeholder="Выберите статус"
                  />
                </div>
                <div v-if="showCloseLeadButton" class="chats-page__lead-close-block">
                  <span class="chats-page__lead-label">Завершить сделку</span>
                  <div class="chats-page__lead-close-row">
                    <NButton
                      size="small"
                      type="success"
                      class="chats-page__lead-close-btn"
                      :disabled="wonStatusId == null"
                      :loading="store.closingLead"
                      @click="onCloseLead(wonStatusId)"
                    >
                      Успешная продажа
                    </NButton>
                    <NButton
                      size="small"
                      type="error"
                      class="chats-page__lead-close-btn"
                      :disabled="lostStatusId == null"
                      :loading="store.closingLead"
                      @click="onCloseLead(lostStatusId)"
                    >
                      Неуспешная продажа
                    </NButton>
                  </div>
                </div>
              </div>
              <div class="chats-page__lead-field chats-page__lead-field--comment">
                <span class="chats-page__lead-label">Комментарий к сделке</span>
                <NInput
                  v-model:value="leadCommentDraft"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                  placeholder="Новый комментарий…"
                  :disabled="savingLeadComment"
                  @keydown.ctrl.enter.prevent="saveLeadComment"
                />
                <NButton
                  size="small"
                  quaternary
                  class="chats-page__lead-save"
                  :loading="savingLeadComment"
                  @click="saveLeadComment"
                >
                  Добавить комментарий
                </NButton>
              </div>
              </div>
            </div>

          </header>



          <TakeoverBadge

            :takeover="store.activeTakeover"

            :chat-id="store.currentChatId"

            @released="onTakeoverReleased"

          />

          <NAlert
            v-if="store.leadClosedBanner"
            type="info"
            :bordered="false"
            class="chats-page__lead-closed-banner"
          >
            Сделка закрыта. Показан весь чат.
          </NAlert>

          <NTabs
            v-model:value="messageScopeTab"
            type="segment"
            size="small"
            class="chats-page__message-scope"
          >
            <NTab name="current_lead" tab="Текущая сделка" />
            <NTab name="all" tab="Весь чат" />
          </NTabs>

          <MessageList

            :messages="store.messages"

            :loading="store.messagesLoading"

            :chat-id="store.currentChatId"

            :contact-id="store.currentChat.contact_id"

            :contact-name="store.currentChat.contact_name"

            @load-older="store.loadOlderMessages()"

          />



          <MessageInput :disabled="store.isInputBlocked" @send="onSend" />

        </template>



        <div v-else class="chats-page__placeholder">

          <MessageSquare :size="48" stroke-width="1.25" />

          <p>Выберите чат из списка</p>

        </div>

      </main>

      <aside v-if="!isNarrow" class="chats-page__inbox-pane">
        <ChatsNotificationsPane />
      </aside>

    </div>

    <div
      v-if="isNarrow && transferInboxOpen"
      class="chats-page__inbox-drawer"
      role="dialog"
      aria-label="Уведомления"
    >
      <div class="chats-page__inbox-drawer-backdrop" @click="transferInboxOpen = false" />
      <aside class="chats-page__inbox-drawer-panel">
        <NButton quaternary size="small" class="chats-page__inbox-close" @click="transferInboxOpen = false">
          Закрыть
        </NButton>
        <ChatsNotificationsPane />
      </aside>
    </div>



    <TransferCardDialog

      v-model:show="transferCardVisible"

      :contact-id="store.currentChat?.contact_id ?? null"

      :group-id="transferGroupId"

      :contact-name="store.currentChat?.contact_name"

      :group-name="transferGroupName"

      :card-owner-user-id="store.currentChat?.card_owner_user_id ?? null"

      @transferred="onCardTransferred()"

    />

  </section>

</template>



<style scoped>

.chats-page {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - var(--app-topbar-height) - 2 * var(--app-content-padding));
  max-height: calc(100dvh - var(--app-topbar-height) - 2 * var(--app-content-padding));
  min-height: 480px;
  overflow: hidden;
}

.chats-page__header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}



.chats-page__title {

  margin: 0;

  font-size: 1.5rem;

  font-weight: 700;

}



.chats-page__tabs {

  margin-bottom: 12px;

}



.chats-page__split {

  flex: 1;

  display: grid;

  grid-template-columns: minmax(260px, 320px) 1fr minmax(320px, 360px);

  gap: 0;

  border: 1px solid var(--app-border);

  border-radius: 8px;

  overflow: hidden;

  min-height: 0;

}



.chats-page__list-pane {

  border-right: 1px solid var(--app-border);

  padding: 12px;

  overflow-y: auto;

  background: var(--app-surface);

}



.chats-page__filters {

  margin-bottom: 12px;

}

.chats-page__unread-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.875rem;
  cursor: pointer;
}

.chats-page__skeleton {
  margin-top: 8px;
}



.chats-page__list {

  list-style: none;

  margin: 0;

  padding: 0;

}



.chats-page__list-item {

  padding: 10px 12px;

  border-radius: 8px;

  cursor: pointer;

  margin-bottom: 4px;

  transition: background 0.15s;

}



.chats-page__list-item:hover {

  background: var(--app-surface-elevated, #f4f4f5);

}



.chats-page__list-item--active {

  background: var(--app-accent-soft, #e8f3ff);

}



.chats-page__list-item--highlight,

.chats-page__list-item--needs-response {

  box-shadow: inset 3px 0 0 var(--app-accent, #2080f0);

}



.chats-page__list-item--needs-response {

  box-shadow: inset 3px 0 0 #d03050;

}



.chats-page__list-row {

  display: flex;

  justify-content: space-between;

  align-items: center;

  gap: 8px;

}

.chats-page__list-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chats-page__chat-header-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.chats-page__back {
  flex-shrink: 0;
  margin-top: 2px;
}



.chats-page__owner {

  margin-top: 4px;

}



.chats-page__preview {

  margin: 4px 0 0;

  font-size: 0.85rem;

  opacity: 0.8;

  overflow: hidden;

  text-overflow: ellipsis;

  white-space: nowrap;

}



.chats-page__meta {

  font-size: 0.75rem;

  opacity: 0.65;

}



.chats-page__chat-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--app-bg);
}

.chats-page__message-scope,
.chats-page__lead-closed-banner {
  flex-shrink: 0;
}

.chats-page__message-scope {
  padding: 8px 12px 0;
}

.chats-page__inbox-pane {

  border-left: 1px solid var(--app-border);

  padding: 12px;

  overflow-y: auto;

  background: var(--app-surface);

}



.chats-page__chat-header {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--app-border);
}

.chats-page__chat-header-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.chats-page__chat-identity {
  min-width: 0;
  flex: 1;
}

.chats-page__chat-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}



.chats-page__chat-header h2 {

  margin: 0 0 4px;

  font-size: 1.1rem;

}



.chats-page__chat-sub {

  display: block;

  font-size: 0.8rem;

  opacity: 0.7;

  margin-top: 4px;

}

.chats-page__lead-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--app-surface-2, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--app-border);
}

.chats-page__lead-panel--collapsed {
  gap: 0;
  padding: 8px 12px;
}

.chats-page__lead-panel-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.chats-page__lead-panel-toggle:hover {
  opacity: 0.9;
}

.chats-page__lead-panel-toggle-title {
  font-size: 0.8125rem;
  font-weight: 600;
}

.chats-page__lead-panel-toggle-tag {
  flex-shrink: 0;
}

.chats-page__lead-panel-chevron {
  flex-shrink: 0;
  margin-left: auto;
  opacity: 0.65;
  transition: transform 0.2s ease;
}

.chats-page__lead-panel-chevron--collapsed {
  transform: rotate(-90deg);
}

.chats-page__lead-panel-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chats-page__lead-panel-toolbar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
}

.chats-page__lead-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.chats-page__lead-field--comment {
  flex: 1;
  width: 100%;
}

.chats-page__lead-label {
  font-size: 0.75rem;
  font-weight: 500;
  opacity: 0.65;
  line-height: 1.2;
}

.chats-page__lead-field--status {
  width: 100%;
}

.chats-page__lead-status {
  width: min(320px, 100%);
}

.chats-page__lead-close-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chats-page__lead-close-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.chats-page__lead-close-btn {
  flex: 1 1 160px;
  min-width: 0;
}

.chats-page__status-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chats-page__status-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12);
}

.chats-page__status-option-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.chats-page__status-menu) {
  min-width: 280px !important;
}

.chats-page__lead-save {
  align-self: flex-start;
}



.chats-page__placeholder {

  flex: 1;

  display: flex;

  flex-direction: column;

  align-items: center;

  justify-content: center;

  gap: 12px;

  opacity: 0.5;

}



@media (max-width: 1023px) {
  .chats-page__split {
    grid-template-columns: 1fr;
  }

  .chats-page__split--narrow .chats-page__list-pane,
  .chats-page__split--narrow .chats-page__chat-pane {
    display: none;
  }

  .chats-page__split--narrow.chats-page__split--show-list .chats-page__list-pane {
    display: block;
    border-right: none;
  }

  .chats-page__split--narrow.chats-page__split--show-chat .chats-page__chat-pane {
    display: flex;
  }

  .chats-page__inbox-pane {
    display: none;
  }
}

.chats-page__inbox-drawer {
  position: fixed;
  inset: 0;
  z-index: 40;
}

.chats-page__inbox-drawer-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
}

.chats-page__inbox-drawer-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: min(360px, 92vw);
  height: 100%;
  background: var(--app-surface);
  padding: 12px;
  overflow-y: auto;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
}

.chats-page__inbox-close {
  margin-bottom: 8px;
}

</style>



