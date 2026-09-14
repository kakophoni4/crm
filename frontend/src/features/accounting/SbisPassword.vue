<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { NButton, NInput, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
const props = defineProps<{ unitId: number; accountantId?: number | null }>()
const auth = useAuthStore(),
  message = useMessage(),
  mode = ref<'closed' | 'view' | 'edit'>('closed'),
  value = ref(''),
  busy = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
function close() {
  clearTimeout(timer)
  value.value = ''
  mode.value = 'closed'
}
onBeforeUnmount(close)
async function reveal() {
  busy.value = true
  try {
    const { data } = await http.post(`/accounting/units/${props.unitId}/sbis-password/reveal`)
    value.value = data.password ?? ''
    mode.value = 'view'
    timer = setTimeout(close, 30000)
  } catch (e) {
    message.error(e instanceof AppError ? e.message : 'Не удалось получить пароль')
  } finally {
    busy.value = false
  }
}
async function save() {
  busy.value = true
  try {
    await http.patch(`/accounting/units/${props.unitId}/card`, {
      sbis_password: value.value || null,
    })
    message.success(value.value ? 'Пароль сохранён' : 'Пароль удалён')
    close()
  } catch (e) {
    message.error(e instanceof AppError ? e.message : 'Не удалось сохранить пароль')
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="sbis-secret">
    <template v-if="auth.isAdmin || (auth.isAccountant && props.accountantId === auth.user?.id)"
      ><template v-if="mode === 'closed'"
        ><span aria-label="Пароль скрыт">********</span
        ><NButton size="small" :loading="busy" @click="reveal">Показать</NButton
        ><NButton size="small" :disabled="busy" @click="mode = 'edit'">Изменить</NButton></template
      ><template v-else
        ><NInput
          v-model:value="value"
          :type="mode === 'view' ? 'text' : 'password'"
          show-password-on="click"
          :readonly="mode === 'view'"
          :disabled="busy"
          :input-props="{ autocomplete: 'new-password', 'aria-label': 'Пароль СБИС' }"
          placeholder="Пароль не задан"
        /><NButton v-if="mode === 'edit'" size="small" :loading="busy" @click="save"
          >Сохранить пароль</NButton
        ><NButton size="small" :disabled="busy" @click="close">Скрыть</NButton></template
      ></template
    ><span v-else>Доступен назначенному бухгалтеру и администратору</span>
  </div>
</template>
<style scoped>
.sbis-secret {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
}
.sbis-secret :deep(.n-input) {
  width: 100%;
  min-width: 0;
}
</style>
