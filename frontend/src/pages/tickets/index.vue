<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { Plus, RefreshCw, Ticket } from 'lucide-vue-next'
import { computed, h, onMounted, ref } from 'vue'

import {
  addTicketCompanies,
  checkAllTicketCompanies,
  checkTicketCompany,
  createSmertnikiTicket,
  healSmertnikiTicket,
  listSmertnikiTickets,
  listTicketCompanies,
  patchTicketCompany,
} from '@/features/tickets/api'
import {
  TICKET_STATUS_OPTIONS,
  TICKET_TYPE_OPTIONS,
  ticketTypeLabel,
  type SmertnikiCompany,
  type SmertnikiTicket,
} from '@/features/tickets/types'
import { AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()
const dialog = useDialog()

const activeTab = ref<'shops' | 'tickets'>('shops')
const loadingCompanies = ref(false)
const loadingTickets = ref(false)
const checkingAll = ref(false)
const addingInns = ref(false)
const companies = ref<SmertnikiCompany[]>([])
const tickets = ref<SmertnikiTicket[]>([])
const innsText = ref('')
const ticketStatus = ref<string>('in_progress')
const issueTypeFilter = ref<string | null>(null)
const createOpen = ref(false)
const createBusy = ref(false)
const createForm = ref({
  company_id: null as number | null,
  issue_type: 'address',
  title: '',
  details: '',
})

const companyOptions = computed<SelectOption[]>(() =>
  companies.value.map((row) => ({
    label: `${row.short_name || row.name || 'Без названия'} · ${row.inn || row.ogrn}`,
    value: row.id,
  })),
)

function flagTags(row: SmertnikiCompany): string[] {
  const flags: string[] = []
  if (row.unreliable_address) flags.push('адрес')
  if (row.unreliable_director) flags.push('ДЛ')
  if (row.unreliable_founder) flags.push('учредитель')
  if (row.is_liquidating) flags.push('ликвидация')
  if (row.is_liquidated) flags.push('исключена')
  return flags
}

function formatChecked(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

async function loadCompanies(): Promise<void> {
  loadingCompanies.value = true
  try {
    const data = await listTicketCompanies()
    companies.value = data.items ?? []
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить лавки')
  } finally {
    loadingCompanies.value = false
  }
}

async function loadTickets(): Promise<void> {
  loadingTickets.value = true
  try {
    const data = await listSmertnikiTickets({
      issue_type: issueTypeFilter.value || undefined,
      status: ticketStatus.value || undefined,
    })
    tickets.value = data.items ?? []
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить тикеты')
  } finally {
    loadingTickets.value = false
  }
}

async function refreshAll(): Promise<void> {
  await Promise.all([loadCompanies(), loadTickets()])
}

function extractInns(raw: string): string[] {
  const found: string[] = []
  for (const match of raw.matchAll(/\d{10,12}/g)) {
    const inn = match[0]
    if (!found.includes(inn)) found.push(inn)
  }
  return found
}

async function onAddInns(): Promise<void> {
  const inns = extractInns(innsText.value)
  if (!inns.length) {
    message.warning('Вставьте ИНН')
    return
  }
  addingInns.value = true
  try {
    await addTicketCompanies(inns, true)
    innsText.value = ''
    message.success(`Отправлено ${inns.length} ИНН`)
    await loadCompanies()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить ИНН')
  } finally {
    addingInns.value = false
  }
}

async function onCheck(row: SmertnikiCompany): Promise<void> {
  try {
    await checkTicketCompany(row.id)
    message.success('Проверка запущена')
    await loadCompanies()
    await loadTickets()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось проверить')
  }
}

async function onCheckAll(): Promise<void> {
  checkingAll.value = true
  try {
    await checkAllTicketCompanies()
    message.success('Проверка всех лавок запущена')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось запустить проверку')
  } finally {
    checkingAll.value = false
  }
}

async function onToggleActive(row: SmertnikiCompany): Promise<void> {
  try {
    const updated = await patchTicketCompany(row.id, { is_active: !row.is_active })
    companies.value = companies.value.map((item) => (item.id === row.id ? { ...item, ...updated } : item))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  }
}

function onHeal(row: SmertnikiTicket): void {
  dialog.warning({
    title: 'Вылечить тикет?',
    content: `${row.title || ticketTypeLabel(row.issue_type)} — ${row.company_name || row.company_inn || row.company_id}`,
    positiveText: 'Вылечена',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      try {
        await healSmertnikiTicket(row.id)
        message.success('Тикет закрыт')
        await loadTickets()
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Не удалось закрыть тикет')
      }
    },
  })
}

async function onCreateTicket(): Promise<void> {
  if (createForm.value.company_id == null || !createForm.value.title.trim()) {
    message.warning('Выберите лавку и укажите заголовок')
    return
  }
  createBusy.value = true
  try {
    await createSmertnikiTicket({
      company_id: createForm.value.company_id,
      issue_type: createForm.value.issue_type,
      title: createForm.value.title.trim(),
      details: createForm.value.details.trim() || null,
    })
    createOpen.value = false
    createForm.value = { company_id: null, issue_type: 'address', title: '', details: '' }
    message.success('Тикет создан')
    activeTab.value = 'tickets'
    await loadTickets()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать тикет')
  } finally {
    createBusy.value = false
  }
}

const companyColumns: DataTableColumns<SmertnikiCompany> = [
  {
    title: 'ИНН',
    key: 'inn',
    width: 130,
    render: (row) => row.inn || '—',
  },
  {
    title: 'Название',
    key: 'name',
    minWidth: 200,
    ellipsis: { tooltip: true },
    render: (row) => row.short_name || row.name || '—',
  },
  {
    title: 'Флаги',
    key: 'flags',
    minWidth: 180,
    render: (row) => {
      const flags = flagTags(row)
      if (!flags.length) return '—'
      return h(
        'div',
        { style: 'display:flex;gap:4px;flex-wrap:wrap' },
        flags.map((flag) => h(NTag, { size: 'small', type: 'warning', bordered: false }, { default: () => flag })),
      )
    },
  },
  {
    title: 'Статус',
    key: 'status_text',
    width: 140,
    ellipsis: { tooltip: true },
    render: (row) => row.status_text || (row.is_active ? 'в мониторинге' : 'выключена'),
  },
  {
    title: 'Проверка',
    key: 'last_checked_at',
    width: 160,
    render: (row) => formatChecked(row.last_checked_at),
  },
  {
    title: '',
    key: 'actions',
    width: 210,
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' }, [
        h(
          NButton,
          { size: 'tiny', onClick: () => onCheck(row) },
          { default: () => 'Проверить' },
        ),
        h(
          NButton,
          { size: 'tiny', tertiary: true, onClick: () => onToggleActive(row) },
          { default: () => (row.is_active ? 'Выключить' : 'Включить') },
        ),
      ]),
  },
]

const ticketColumns: DataTableColumns<SmertnikiTicket> = [
  {
    title: 'Компания',
    key: 'company_name',
    minWidth: 200,
    ellipsis: { tooltip: true },
    render: (row) => `${row.company_name || '—'} · ${row.company_inn || ''}`,
  },
  {
    title: 'Тип',
    key: 'issue_type',
    width: 160,
    render: (row) => ticketTypeLabel(row.issue_type),
  },
  {
    title: 'Статус',
    key: 'status',
    width: 120,
    render: (row) => TICKET_STATUS_OPTIONS.find((item) => item.value === row.status)?.label ?? row.status,
  },
  {
    title: 'Возраст',
    key: 'age_days',
    width: 100,
    render: (row) => `${row.age_days} дн.`,
  },
  {
    title: '',
    key: 'actions',
    width: 120,
    render: (row) =>
      row.status === 'in_progress'
        ? h(NButton, { size: 'tiny', type: 'primary', onClick: () => onHeal(row) }, { default: () => 'Вылечить' })
        : null,
  },
]

onMounted(() => {
  void refreshAll()
})
</script>

<template>
  <div class="tickets-page">
    <header class="tickets-page__header">
      <h1 class="tickets-page__title">
        <Ticket :size="22" />
        Тикеты ЕГРЮЛ
      </h1>
      <div class="tickets-page__header-actions">
        <NButton @click="createOpen = true">
          <template #icon><Plus :size="16" /></template>
          Новый тикет
        </NButton>
        <NButton :loading="checkingAll" @click="onCheckAll">Проверить все</NButton>
        <NButton :loading="loadingCompanies || loadingTickets" @click="refreshAll">
          <template #icon><RefreshCw :size="16" /></template>
          Обновить
        </NButton>
      </div>
    </header>

    <AppCard>
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane name="shops" tab="Лавки">
          <div class="tickets-page__filters">
            <NInput
              v-model:value="innsText"
              type="textarea"
              placeholder="Вставьте ИНН — по одному или списком"
              :autosize="{ minRows: 2, maxRows: 6 }"
              style="flex: 1; min-width: 280px"
            />
            <NButton type="primary" :loading="addingInns" @click="onAddInns">Догрузить ИНН</NButton>
          </div>
          <NSpin :show="loadingCompanies && companies.length === 0">
            <NEmpty v-if="!loadingCompanies && companies.length === 0" description="Нет лавок" />
            <NDataTable
              v-else
              :columns="companyColumns"
              :data="companies"
              :row-key="(row: SmertnikiCompany) => row.id"
              :bordered="false"
              size="small"
              :scroll-x="1100"
            />
          </NSpin>
        </NTabPane>
        <NTabPane name="tickets" tab="Тикеты">
          <div class="tickets-page__filters">
            <NSelect
              v-model:value="issueTypeFilter"
              :options="TICKET_TYPE_OPTIONS"
              clearable
              placeholder="Тип"
              style="min-width: 200px"
              @update:value="loadTickets"
            />
            <NSelect
              v-model:value="ticketStatus"
              :options="TICKET_STATUS_OPTIONS"
              placeholder="Статус"
              style="min-width: 180px"
              @update:value="loadTickets"
            />
          </div>
          <NSpin :show="loadingTickets && tickets.length === 0">
            <NEmpty v-if="!loadingTickets && tickets.length === 0" description="Нет тикетов" />
            <NDataTable
              v-else
              :columns="ticketColumns"
              :data="tickets"
              :row-key="(row: SmertnikiTicket) => row.id"
              :bordered="false"
              size="small"
              :scroll-x="900"
            />
          </NSpin>
        </NTabPane>
      </NTabs>
    </AppCard>

    <NModal v-model:show="createOpen" preset="card" title="Новый тикет" style="max-width: 520px">
      <NForm>
        <NFormItem label="Лавка">
          <NSelect
            v-model:value="createForm.company_id"
            :options="companyOptions"
            filterable
            placeholder="Компания"
          />
        </NFormItem>
        <NFormItem label="Тип">
          <NSelect v-model:value="createForm.issue_type" :options="TICKET_TYPE_OPTIONS" />
        </NFormItem>
        <NFormItem label="Заголовок">
          <NInput v-model:value="createForm.title" />
        </NFormItem>
        <NFormItem label="Детали">
          <NInput v-model:value="createForm.details" type="textarea" :autosize="{ minRows: 3 }" />
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="tickets-page__modal-actions">
          <NButton @click="createOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="createBusy" @click="onCreateTicket">Создать</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.tickets-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tickets-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.tickets-page__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.tickets-page__header-actions,
.tickets-page__filters,
.tickets-page__modal-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tickets-page__filters {
  margin-bottom: 12px;
}

.tickets-page__modal-actions {
  justify-content: flex-end;
}
</style>
