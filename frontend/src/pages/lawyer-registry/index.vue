<script setup lang="ts">
import type { SelectOption, UploadCustomRequestOptions } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NDatePicker,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NUpload,
  useMessage,
} from 'naive-ui'
import { Building2, Pin, Plus, Upload } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import {
  addLawyerPayment,
  createLawyerDirector,
  createLawyerShop,
  getLawyerDirector,
  importLawyerSvodnaya,
  listLawyerAlerts,
  listLawyerRegistry,
  markLawyerAlertsRead,
  patchLawyerDirector,
  patchLawyerShop,
  type LawyerAlert,
  type LawyerDirector,
  type LawyerShop,
} from '@/features/lawyer-registry/api'
import {
  ACCOUNT_STATUS_OPTIONS,
  COMPANY_STATUS_OPTIONS,
  ECSP_OPTIONS,
  SHOP_KIND_OPTIONS,
  UNRELIABLE_OPTIONS,
  ZSK_OPTIONS,
} from '@/features/lawyer-registry/types'
import { AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()
const loading = ref(false)
const directors = ref<LawyerDirector[]>([])
const orphans = ref<LawyerShop[]>([])
const pinned = ref<LawyerShop[]>([])
const details = ref<Record<number, LawyerDirector>>({})
const expanded = ref<string[]>([])
const alerts = ref<LawyerAlert[]>([])
const unread = ref(0)
const totalShops = ref(0)

const q = ref('')
const kind = ref<string | null>(null)
const companyStatus = ref<string | null>(null)
const unreliable = ref<string | null>(null)
const zsk = ref<string | null>(null)
const ecsp = ref<string | null>(null)
const manager = ref('')
const dirovod = ref('')
const showHidden = ref(false)

const shopOpen = ref(false)
const directorOpen = ref(false)
const payOpen = ref(false)
const shopForm = ref({
  inn: '',
  name: '',
  director_name: '',
  kind: 'new',
  registered_at: null as number | null,
})
const directorForm = ref({ full_name: '', salary_plan: null as number | null, dirovod: '' })
const payForm = ref({
  director_id: 0,
  shop_id: null as number | null,
  period_ym: currentPeriod(),
  amount: 10000,
})

function currentPeriod(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function toIsoDate(value: number | null | undefined): string | null {
  if (value == null) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function fromIsoDate(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

function shopsOf(director: LawyerDirector): LawyerShop[] {
  const shops = director.shops ?? []
  if (showHidden.value) return shops
  return shops.filter((shop) => !shop.hidden_at)
}

function kindLabel(value: string): string {
  return SHOP_KIND_OPTIONS.find((item) => item.value === value)?.label ?? value
}

const UNRELIABLE_ALIASES: Record<string, string> = {
  налог: 'Налог',
  адрес: 'Адрес',
  'должност.лицо': 'Должност.лицо',
  'должност. лицо': 'Должност.лицо',
  'должностное лицо': 'Должност.лицо',
}

function csvValues(value: string | null | undefined): string[] {
  if (!value) return []
  return value
    .split(/[,;]/)
    .map((part) => {
      const trimmed = part.trim()
      return UNRELIABLE_ALIASES[trimmed.toLowerCase()] ?? trimmed
    })
    .filter(Boolean)
}

function csvJoin(values: string[] | null): string | null {
  if (!values?.length) return null
  return values.join(', ')
}

function money(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${new Intl.NumberFormat('ru-RU').format(value)} ₽`
}

function periodLabel(value: string): string {
  const [year, month] = value.split('-')
  const names = [
    'янв', 'фев', 'мар', 'апр', 'май', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
  ]
  const idx = Number(month) - 1
  return `${names[idx] ?? month} ${year}`
}

async function toggleHidden(): Promise<void> {
  showHidden.value = !showHidden.value
  await loadTree()
}

async function loadTree(): Promise<void> {
  loading.value = true
  try {
    const data = await listLawyerRegistry({
      q: q.value,
      kind: kind.value,
      company_status: companyStatus.value,
      unreliable: unreliable.value,
      zsk: zsk.value,
      ecsp_status: ecsp.value,
      manager: manager.value,
      dirovod: dirovod.value,
      include_hidden: showHidden.value,
    })
    directors.value = data.items
    orphans.value = data.orphan_shops
    pinned.value = data.pinned_shops
    totalShops.value = data.total_shops
    unread.value = data.unread_alerts
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить реестр')
  } finally {
    loading.value = false
  }
}

async function loadAlerts(): Promise<void> {
  try {
    const data = await listLawyerAlerts()
    alerts.value = data.items
    unread.value = data.unread
  } catch {
    alerts.value = []
  }
}

async function onExpand(keys: string | string[]): Promise<void> {
  const list = (Array.isArray(keys) ? keys : [keys]).map(String)
  const added = list.filter((key) => !expanded.value.includes(key))
  expanded.value = list
  for (const key of added) {
    const id = Number(key.replace('d-', ''))
    if (!Number.isFinite(id) || details.value[id]) continue
    try {
      details.value[id] = await getLawyerDirector(id)
    } catch (err) {
      message.error(err instanceof AppError ? err.message : 'Не удалось открыть директора')
    }
  }
}

async function saveDirector(id: number, patch: Record<string, unknown>): Promise<void> {
  try {
    details.value[id] = await patchLawyerDirector(id, patch)
    await loadTree()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  }
}

async function saveShop(id: number, patch: Record<string, unknown>, directorId?: number): Promise<void> {
  try {
    await patchLawyerShop(id, patch)
    if (directorId) details.value[directorId] = await getLawyerDirector(directorId)
    await loadTree()
    if (patch.hidden === true) message.success('Лавка скрыта. Вернуть можно через «Показать скрытые»')
    else if (patch.hidden === false) message.success('Лавка снова в списке')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить лавку')
  }
}

async function submitShop(): Promise<void> {
  try {
    await createLawyerShop({
      inn: shopForm.value.inn.trim(),
      name: shopForm.value.name.trim(),
      director_name: shopForm.value.director_name.trim() || null,
      kind: shopForm.value.kind,
      registered_at: toIsoDate(shopForm.value.registered_at),
    })
    message.success('Лавка добавлена и отправлена в парсер ЕГРЮЛ')
    shopOpen.value = false
    shopForm.value = { inn: '', name: '', director_name: '', kind: 'new', registered_at: null }
    await loadTree()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить лавку')
  }
}

async function submitDirector(): Promise<void> {
  try {
    await createLawyerDirector({
      full_name: directorForm.value.full_name.trim(),
      salary_plan: directorForm.value.salary_plan,
      dirovod: directorForm.value.dirovod.trim() || null,
    })
    message.success('Директор добавлен')
    directorOpen.value = false
    directorForm.value = { full_name: '', salary_plan: null, dirovod: '' }
    await loadTree()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить директора')
  }
}

function openPay(directorId: number): void {
  payForm.value = {
    director_id: directorId,
    shop_id: null,
    period_ym: currentPeriod(),
    amount: details.value[directorId]?.salary_plan || 10000,
  }
  payOpen.value = true
}

async function submitPay(): Promise<void> {
  try {
    await addLawyerPayment(payForm.value.director_id, {
      shop_id: payForm.value.shop_id,
      period_ym: payForm.value.period_ym,
      amount: payForm.value.amount,
    })
    message.success('Оплата записана')
    payOpen.value = false
    details.value[payForm.value.director_id] = await getLawyerDirector(payForm.value.director_id)
    await loadTree()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить оплату')
  }
}

async function onImport(opts: UploadCustomRequestOptions): Promise<void> {
  const file = opts.file.file
  if (!file) {
    opts.onError()
    return
  }
  try {
    const result = await importLawyerSvodnaya(file)
    message.success(
      `Импорт: новых лавок ${result.shops}, обновлено ${result.updated}, выплат ${result.payments}`,
    )
    opts.onFinish()
    await loadTree()
  } catch (err) {
    opts.onError()
    message.error(err instanceof AppError ? err.message : 'Не удалось импортировать сводную')
  }
}

async function dismissAlerts(): Promise<void> {
  await markLawyerAlertsRead()
  await loadAlerts()
}

const shopOptions = computed<SelectOption[]>(() => {
  const dir = details.value[payForm.value.director_id]
  return (dir?.shops ?? []).map((shop) => ({ label: shop.name, value: shop.id }))
})

onMounted(async () => {
  await Promise.all([loadTree(), loadAlerts()])
})
</script>

<template>
  <div class="registry-page">
    <AppCard title="Лавки и диры">
      <NSpace vertical :size="14">
        <p class="hint">
          Все лавки из сводной, сгруппированные по директору. Поля можно менять. Новая лавка сразу
          уходит в парсер ЕГРЮЛ; обновления с парсера лавок приходят уведомлением.
        </p>
        <NAlert
          v-if="unread"
          type="warning"
          :title="`Новые данные парсера: ${unread}`"
          closable
          @close="dismissAlerts"
        >
          <div v-for="alert in alerts.filter((a) => !a.is_read).slice(0, 6)" :key="alert.id">
            {{ alert.title }} — {{ alert.details }}
          </div>
        </NAlert>
        <NSpace>
          <NButton type="primary" @click="shopOpen = true">
            <template #icon><Plus :size="16" /></template>
            Новая лавка
          </NButton>
          <NButton secondary @click="directorOpen = true">
            <template #icon><Building2 :size="16" /></template>
            Новый дир
          </NButton>
          <NUpload :show-file-list="false" accept=".xlsx" :custom-request="onImport">
            <NButton>
              <template #icon><Upload :size="16" /></template>
              Импорт сводной
            </NButton>
          </NUpload>
          <span class="hint">{{ totalShops }} лавок · {{ directors.length }} диров</span>
        </NSpace>
        <div class="filters">
          <NInput v-model:value="q" clearable placeholder="Поиск: название, ИНН, банки" @keyup.enter="loadTree" />
          <NSelect v-model:value="kind" clearable :options="SHOP_KIND_OPTIONS" placeholder="Тип" />
          <NSelect v-model:value="companyStatus" clearable :options="COMPANY_STATUS_OPTIONS" placeholder="Статус" />
          <NSelect v-model:value="zsk" clearable :options="ZSK_OPTIONS" placeholder="ЗСК" />
          <NSelect v-model:value="ecsp" clearable :options="ECSP_OPTIONS" placeholder="ЭЦП" />
          <NSelect v-model:value="unreliable" clearable :options="UNRELIABLE_OPTIONS" placeholder="Недостоверка" />
          <NInput v-model:value="manager" clearable placeholder="Менеджер" />
          <NInput v-model:value="dirovod" clearable placeholder="Дировод" />
          <NButton @click="loadTree">Найти</NButton>
          <NButton :type="showHidden ? 'warning' : 'default'" @click="toggleHidden">
            {{ showHidden ? 'Скрытые показаны' : 'Показать скрытые' }}
          </NButton>
        </div>
        <div v-if="pinned.length" class="pinned">
          <p class="section-title">Закреплённые лавки</p>
          <button
            v-for="shop in pinned"
            :key="`pin-${shop.id}`"
            type="button"
            class="pin-chip"
            @click="shop.director_id && onExpand([...expanded, `d-${shop.director_id}`])"
          >
            <Pin :size="12" />
            {{ shop.name }}
          </button>
        </div>
        <NSpin :show="loading">
          <NCollapse :expanded-names="expanded" @update:expanded-names="onExpand">
            <NCollapseItem
              v-for="director in directors"
              :key="director.id"
              :name="`d-${director.id}`"
            >
              <template #header>
                <div class="dir-head">
                  <strong>{{ director.full_name }}</strong>
                  <NTag v-if="director.pinned_at" size="small" type="warning">топ</NTag>
                  <span class="meta">{{ director.shop_count }} лавок</span>
                  <span class="meta">ЗП {{ money(director.salary_plan) }}</span>
                  <span class="meta">
                    {{ director.last_paid_period ? `оплачено ${periodLabel(director.last_paid_period)}` : 'оплат нет' }}
                  </span>
                  <span v-if="director.dirovod" class="meta">дировод: {{ director.dirovod }}</span>
                </div>
              </template>
              <div v-if="details[director.id]" class="dir-body">
                <div class="grid">
                  <label>Зарплата
                    <NInputNumber
                      :value="details[director.id].salary_plan"
                      :show-button="false"
                      @update:value="(v) => saveDirector(director.id, { salary_plan: v })"
                    />
                  </label>
                  <label>Дировод
                    <NInput
                      :value="details[director.id].dirovod ?? ''"
                      @blur="(e) => saveDirector(director.id, { dirovod: (e.target as HTMLInputElement).value || null })"
                    />
                  </label>
                  <label>Статус компании дира
                    <NSelect
                      :value="details[director.id].company_status"
                      :options="COMPANY_STATUS_OPTIONS"
                      clearable
                      placeholder="Выбрать"
                      @update:value="(v: string | null) => saveDirector(director.id, { company_status: v })"
                    />
                  </label>
                  <label>Статус компаний
                    <NSelect
                      :value="details[director.id].companies_status"
                      :options="COMPANY_STATUS_OPTIONS"
                      clearable
                      placeholder="Выбрать"
                      @update:value="(v: string | null) => saveDirector(director.id, { companies_status: v })"
                    />
                  </label>
                  <label>ЭЦП
                    <NSelect
                      :value="details[director.id].ecsp_status"
                      :options="ECSP_OPTIONS"
                      clearable
                      placeholder="Выбрать"
                      @update:value="(v: string | null) => saveDirector(director.id, { ecsp_status: v })"
                    />
                  </label>
                  <label>Банки
                    <NInput
                      :value="details[director.id].banks ?? ''"
                      @blur="(e) => saveDirector(director.id, { banks: (e.target as HTMLInputElement).value || null })"
                    />
                  </label>
                  <label>Счета
                    <NSelect
                      :value="details[director.id].accounts_status"
                      :options="ACCOUNT_STATUS_OPTIONS"
                      clearable
                      placeholder="Выбрать"
                      @update:value="(v: string | null) => saveDirector(director.id, { accounts_status: v })"
                    />
                  </label>
                  <label>Телефон
                    <NInput
                      :value="details[director.id].phone ?? ''"
                      @blur="(e) => saveDirector(director.id, { phone: (e.target as HTMLInputElement).value || null })"
                    />
                  </label>
                </div>
                <NSpace style="margin: 10px 0">
                  <NButton size="small" @click="openPay(director.id)">Добавить оплату</NButton>
                  <NButton
                    size="small"
                    quaternary
                    @click="saveDirector(director.id, { pinned: !director.pinned_at })"
                  >
                    {{ director.pinned_at ? 'Открепить дира' : 'Закрепить дира' }}
                  </NButton>
                </NSpace>
                <div v-if="details[director.id].payments.length" class="pays">
                  <span
                    v-for="pay in details[director.id].payments"
                    :key="pay.id"
                    class="pay-chip pay-chip--ok"
                  >
                    {{ periodLabel(pay.period_ym) }} · {{ money(pay.amount) }}
                    <template v-if="pay.shop_name"> · {{ pay.shop_name }}</template>
                  </span>
                </div>
                <NCollapse>
                  <NCollapseItem
                    v-for="shop in shopsOf(details[director.id])"
                    :key="shop.id"
                    :name="`s-${shop.id}`"
                    :title="`${shop.hidden_at ? 'Скрыта · ' : ''}${shop.name} · ${kindLabel(shop.kind)} · ${shop.inn}`"
                  >
                    <div class="grid">
                      <label>Тип
                        <NSelect
                          :value="shop.kind"
                          :options="SHOP_KIND_OPTIONS"
                          size="small"
                          @update:value="(v: string) => saveShop(shop.id, { kind: v }, director.id)"
                        />
                      </label>
                      <label>Статус
                        <NSelect
                          :value="shop.company_status"
                          :options="COMPANY_STATUS_OPTIONS"
                          size="small"
                          clearable
                          placeholder="Выбрать"
                          @update:value="(v: string | null) => saveShop(shop.id, { company_status: v }, director.id)"
                        />
                      </label>
                      <label>Лечение / проблема
                        <NInput
                          :value="shop.treatment_status ?? ''"
                          @blur="(e) => saveShop(shop.id, { treatment_status: (e.target as HTMLInputElement).value || null }, director.id)"
                        />
                      </label>
                      <label>Недостоверка
                        <NSelect
                          :value="csvValues(shop.unreliable)"
                          :options="UNRELIABLE_OPTIONS"
                          size="small"
                          multiple
                          clearable
                          placeholder="Выбрать"
                          @update:value="(v: string[]) => saveShop(shop.id, { unreliable: csvJoin(v) }, director.id)"
                        />
                      </label>
                      <label>ЗСК
                        <NSelect
                          :value="shop.zsk"
                          :options="ZSK_OPTIONS"
                          size="small"
                          clearable
                          placeholder="Выбрать"
                          @update:value="(v: string | null) => saveShop(shop.id, { zsk: v }, director.id)"
                        />
                      </label>
                      <label>ЭЦП
                        <NSelect
                          :value="shop.ecsp_status"
                          :options="ECSP_OPTIONS"
                          size="small"
                          clearable
                          placeholder="Выбрать"
                          @update:value="(v: string | null) => saveShop(shop.id, { ecsp_status: v }, director.id)"
                        />
                      </label>
                      <label>Банки
                        <NInput
                          :value="shop.banks ?? ''"
                          @blur="(e) => saveShop(shop.id, { banks: (e.target as HTMLInputElement).value || null }, director.id)"
                        />
                      </label>
                      <label>Счета
                        <NSelect
                          :value="shop.accounts_status"
                          :options="ACCOUNT_STATUS_OPTIONS"
                          size="small"
                          clearable
                          placeholder="Выбрать"
                          @update:value="(v: string | null) => saveShop(shop.id, { accounts_status: v }, director.id)"
                        />
                      </label>
                      <label>Менеджер
                        <NInput
                          :value="shop.manager ?? ''"
                          @blur="(e) => saveShop(shop.id, { manager: (e.target as HTMLInputElement).value || null }, director.id)"
                        />
                      </label>
                      <label>Регистрация
                        <NDatePicker
                          :value="fromIsoDate(shop.registered_at)"
                          type="date"
                          clearable
                          style="width: 100%"
                          @update:value="(v: number | null) => saveShop(shop.id, { registered_at: toIsoDate(v) }, director.id)"
                        />
                      </label>
                      <label>Плановая выплата
                        <NInputNumber
                          :value="shop.planned_payout"
                          :show-button="false"
                          @update:value="(v) => saveShop(shop.id, { planned_payout: v }, director.id)"
                        />
                      </label>
                    </div>
                    <NSpace style="margin-top: 8px">
                      <NButton
                        size="tiny"
                        quaternary
                        @click="saveShop(shop.id, { pinned: !shop.pinned_at }, director.id)"
                      >
                        {{ shop.pinned_at ? 'Открепить лавку' : 'Закрепить лавку сверху' }}
                      </NButton>
                      <NButton
                        size="tiny"
                        quaternary
                        @click="saveShop(shop.id, { hidden: !shop.hidden_at }, director.id)"
                      >
                        {{ shop.hidden_at ? 'Вернуть в список' : 'Скрыть лавку' }}
                      </NButton>
                    </NSpace>
                    <p class="hint">ИНН {{ shop.inn }}</p>
                  </NCollapseItem>
                </NCollapse>
              </div>
              <p v-else class="hint">Открываю…</p>
            </NCollapseItem>
            <NCollapseItem v-if="orphans.length" name="orphans" title="Лавки без директора">
              <div v-for="shop in orphans" :key="shop.id" class="orphan">
                {{ shop.name }} · {{ shop.inn }}
              </div>
            </NCollapseItem>
          </NCollapse>
        </NSpin>
      </NSpace>
    </AppCard>

    <NModal v-model:show="shopOpen" preset="card" title="Новая лавка" style="width: 420px">
      <NSpace vertical>
        <NInput v-model:value="shopForm.inn" placeholder="ИНН" />
        <NInput v-model:value="shopForm.name" placeholder="Название" />
        <NInput v-model:value="shopForm.director_name" placeholder="ФИО директора" />
        <NSelect v-model:value="shopForm.kind" :options="SHOP_KIND_OPTIONS" />
        <NDatePicker
          v-model:value="shopForm.registered_at"
          type="date"
          clearable
          placeholder="Дата регистрации"
          style="width: 100%"
        />
        <NButton type="primary" block @click="submitShop">Добавить в реестр и парсер</NButton>
      </NSpace>
    </NModal>

    <NModal v-model:show="directorOpen" preset="card" title="Новый директор" style="width: 420px">
      <NSpace vertical>
        <NInput v-model:value="directorForm.full_name" placeholder="ФИО" />
        <NInputNumber
          v-model:value="directorForm.salary_plan"
          :show-button="false"
          placeholder="Зарплата"
          style="width: 100%"
        />
        <NInput v-model:value="directorForm.dirovod" placeholder="Дировод" />
        <NButton type="primary" block @click="submitDirector">Создать</NButton>
      </NSpace>
    </NModal>

    <NModal v-model:show="payOpen" preset="card" title="Оплата директору" style="width: 420px">
      <NSpace vertical>
        <NInput v-model:value="payForm.period_ym" placeholder="Период ГГГГ-ММ" />
        <NInputNumber v-model:value="payForm.amount" :show-button="false" style="width: 100%" />
        <NSelect
          v-model:value="payForm.shop_id"
          :options="shopOptions"
          clearable
          placeholder="Лавка (необязательно)"
        />
        <NButton type="primary" block @click="submitPay">Записать оплату</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.registry-page {
  width: 100%;
}
.hint {
  color: var(--app-text-muted);
  font-size: 0.8125rem;
  margin: 0;
}
.filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.dir-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}
.meta {
  color: var(--app-text-muted);
  font-size: 0.8rem;
}
.dir-body {
  padding: 8px 0 4px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--app-text-muted);
}
.grid :deep(.n-select),
.grid :deep(.n-input),
.grid :deep(.n-input-number),
.grid :deep(.n-date-picker) {
  width: 100%;
}
.pays {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.pay-chip {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-border) 70%, transparent);
}
.pay-chip--ok {
  background: color-mix(in srgb, #16a34a 18%, transparent);
}
.pinned {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.section-title {
  width: 100%;
  margin: 0;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}
.pin-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--app-border);
  background: transparent;
  border-radius: 999px;
  padding: 4px 8px;
  cursor: pointer;
  font: inherit;
}
.orphan {
  padding: 6px 0;
  font-size: 0.9rem;
}
</style>
