<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { NButton, NDataTable, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import type { BotItem, Group } from '@/features/admin/api'
import { listBots, listGroups, setBotGroupAssignments } from '@/features/admin/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const message = useMessage()
const auth = useAuthStore()
const loading = ref(false)
const savingId = ref<number | null>(null)
const rows = ref<BotItem[]>([])
const groups = ref<Group[]>([])
const draftGroupIds = ref<Record<number, number[]>>({})

const groupOptions = computed<SelectOption[]>(() =>
  groups.value.map((g) => ({ label: g.name, value: g.id })),
)

const columns = computed<DataTableColumns<BotItem>>(() => [
  { title: 'Код', key: 'code', width: 140 },
  { title: 'Название', key: 'name' },
  {
    title: 'Отдел',
    key: 'department_name',
    width: 160,
    render: (row) => row.department_name ?? `#${row.department_id}`,
  },
  {
    title: 'Группы',
    key: 'assigned_group_ids',
    minWidth: 280,
    render: (row) =>
      h(NSelect, {
        multiple: true,
        filterable: true,
        value: draftGroupIds.value[row.id] ?? row.assigned_group_ids,
        options: groupOptions.value,
        placeholder: 'Не распределён',
        onUpdateValue: (value: number[]) => {
          draftGroupIds.value[row.id] = value
        },
      }),
  },
  {
    title: '',
    key: 'actions',
    width: 120,
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          type: 'primary',
          loading: savingId.value === row.id,
          onClick: () => onSave(row),
        },
        { default: () => 'Сохранить' },
      ),
  },
])

async function load(): Promise<void> {
  loading.value = true
  try {
    const deptId = auth.user?.department_id ?? undefined
    groups.value = await listGroups(deptId)
    rows.value = await listBots()
    draftGroupIds.value = Object.fromEntries(
      rows.value.map((row) => [row.id, [...row.assigned_group_ids]]),
    )
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить ботов')
  } finally {
    loading.value = false
  }
}

async function onSave(row: BotItem): Promise<void> {
  savingId.value = row.id
  try {
    const groupIds = draftGroupIds.value[row.id] ?? row.assigned_group_ids
    const updated = await setBotGroupAssignments(row.id, groupIds)
    rows.value = rows.value.map((item) => (item.id === updated.id ? updated : item))
    draftGroupIds.value[row.id] = [...updated.assigned_group_ids]
    message.success('Распределение сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')
  } finally {
    savingId.value = null
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <div>
        <h1 class="admin-page__title">Боты отдела</h1>
        <p class="admin-page__hint">
          Выберите группы, которым доступен бот. Если групп нет — чаты идут в общий ящик отдела.
        </p>
      </div>
    </header>
    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(r: BotItem) => r.id" />
    </NSpin>
  </section>
</template>

<style scoped>
.admin-page__header {
  margin-bottom: 16px;
}

.admin-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.admin-page__hint {
  margin: 6px 0 0;
  color: var(--app-text-muted);
  font-size: 0.875rem;
}
</style>
