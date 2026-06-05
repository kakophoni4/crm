<script setup lang="ts">

import type { DataTableColumns } from 'naive-ui'

import {

  NButton,

  NDataTable,

  NForm,

  NFormItem,

  NInput,

  NInputNumber,

  NModal,

  NSpace,

  NSpin,

  NTag,

  useMessage,

} from 'naive-ui'

import { computed, h, onMounted, ref } from 'vue'



import type { StatusItem } from '@/features/admin/api'

import { createStatus, deleteStatus, listStatuses, updateStatus } from '@/features/admin/api'

import {

  isPipelineStageDeletable,

  isPipelineStageVisibleInAdmin,

} from '@/features/leads/pipeline-constants'

import { AppError } from '@/shared/api/http'



type StatusKind = StatusItem['kind']



const message = useMessage()

const activeKind = ref<StatusKind>('lead_pipeline')

const loading = ref(false)

const rows = ref<StatusItem[]>([])

const showModal = ref(false)

const editing = ref<StatusItem | null>(null)

const form = ref({

  code: '',

  kind: 'lead_pipeline' as StatusKind,

  label: '',

  sort_order: 0,

})



const visibleRows = computed(() =>

  rows.value.filter((row) => isPipelineStageVisibleInAdmin(row.code)),

)



const columns = computed<DataTableColumns<StatusItem>>(() => [

  { title: 'Код', key: 'code', width: 140 },

  {

    title: 'Метка',

    key: 'label',

    render: (row) =>

      h(NSpace, { size: 6, align: 'center' }, () => [

        row.label,

        !isPipelineStageDeletable(row.code)

          ? h(NTag, { size: 'small', bordered: false, type: 'info' }, { default: () => 'Системный' })

          : null,

      ]),

  },

  { title: 'Порядок', key: 'sort_order', width: 90 },

  {

    title: '',

    key: 'actions',

    width: 180,

    render: (row) =>

      h(NSpace, null, () => [

        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => 'Изменить' }),

        isPipelineStageDeletable(row.code)

          ? h(

              NButton,

              { size: 'small', type: 'error', quaternary: true, onClick: () => onDelete(row) },

              { default: () => 'Удалить' },

            )

          : null,

      ]),

  },

])



function openCreate(): void {

  editing.value = null

  form.value = {

    code: '',

    kind: activeKind.value,

    label: '',

    sort_order: 0,

  }

  showModal.value = true

}



function openEdit(row: StatusItem): void {

  editing.value = row

  form.value = {

    code: row.code,

    kind: row.kind,

    label: row.label,

    sort_order: row.sort_order,

  }

  showModal.value = true

}



async function load(): Promise<void> {

  loading.value = true

  try {

    rows.value = await listStatuses({ kind: activeKind.value, include_inactive: true })

  } catch (err) {

    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить статусы')

  } finally {

    loading.value = false

  }

}



async function onSave(): Promise<void> {

  if (!form.value.code.trim() || !form.value.label.trim()) {

    message.warning('Заполните код и метку')

    return

  }

  try {

    if (editing.value) {

      await updateStatus(editing.value.id, {

        label: form.value.label.trim(),

        sort_order: form.value.sort_order,

      })

      message.success('Статус обновлён')

    } else {

      await createStatus({

        code: form.value.code.trim(),

        kind: form.value.kind,

        label: form.value.label.trim(),

        sort_order: form.value.sort_order,

      })

      message.success('Статус создан')

    }

    showModal.value = false

    await load()

  } catch (err) {

    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')

  }

}



async function onDelete(row: StatusItem): Promise<void> {

  if (!isPipelineStageDeletable(row.code)) {

    message.warning('Системные этапы (new, in_progress) нельзя удалить — только изменить')

    return

  }

  try {

    await deleteStatus(row.id)

    message.success('Этап удалён')

    await load()

  } catch (err) {

    message.error(err instanceof AppError ? err.message : 'Не удалось удалить')

  }

}



onMounted(() => void load())

</script>



<template>

  <section class="admin-page">

    <header class="admin-page__header">

      <div>

        <h1 class="admin-page__title">Воронка сделок</h1>

      </div>

      <NButton type="primary" @click="openCreate">Добавить этап</NButton>

    </header>



    <NSpin :show="loading">

      <NDataTable :columns="columns" :data="visibleRows" :row-key="(r: StatusItem) => r.id" />

    </NSpin>



    <NModal

      v-model:show="showModal"

      preset="card"

      :title="editing ? 'Редактировать этап' : 'Новый этап воронки'"

      style="max-width: 420px"

    >

      <NForm label-placement="top">

        <NFormItem v-if="!editing" label="Код">

          <NInput v-model:value="form.code" />

        </NFormItem>

        <NFormItem label="Метка">

          <NInput v-model:value="form.label" />

        </NFormItem>

        <NFormItem label="Порядок">

          <NInputNumber v-model:value="form.sort_order" :min="0" class="w-full" />

        </NFormItem>

      </NForm>

      <template #footer>

        <NSpace justify="end">

          <NButton @click="showModal = false">Отмена</NButton>

          <NButton type="primary" @click="onSave">Сохранить</NButton>

        </NSpace>

      </template>

    </NModal>

  </section>

</template>



<style scoped>

.admin-page__header {

  display: flex;

  align-items: flex-start;

  justify-content: space-between;

  margin-bottom: 16px;

  gap: 12px;

}



.admin-page__title {

  margin: 0;

  font-size: 1.5rem;

  font-weight: 700;

}



.w-full {

  width: 100%;

}

</style>

