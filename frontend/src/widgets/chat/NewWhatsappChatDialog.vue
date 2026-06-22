<script setup lang="ts">
import type { BotListItem } from '@/entities/bot/types'
import { startWhatsappOutreach } from '@/features/chats/api'
import { AppError } from '@/shared/api/http'
import { NButton, NForm, NFormItem, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  show: boolean
  bots: BotListItem[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  started: [chatId: number]
}>()

const message = useMessage()
const loading = ref(false)
const phone = ref('')
const fullName = ref('')
const botId = ref<number | null>(null)

const whatsappBots = computed(() =>
  props.bots.filter((bot) => bot.channel === 'whatsapp' && bot.is_active),
)

const botOptions = computed(() =>
  whatsappBots.value.map((bot) => ({ label: bot.name, value: bot.id })),
)

watch(
  () => props.show,
  (visible) => {
    if (!visible) return
    phone.value = ''
    fullName.value = ''
    if (whatsappBots.value.length === 1) {
      botId.value = whatsappBots.value[0]?.id ?? null
    } else {
      botId.value = null
    }
  },
)

function close(): void {
  emit('update:show', false)
}

async function submit(): Promise<void> {
  const digits = phone.value.replace(/\D/g, '')
  const name = fullName.value.trim()
  if (digits.length < 10) {
    message.error('Введите номер WhatsApp с кодом страны (например 79001234567)')
    return
  }
  if (!name) {
    message.error('Введите имя контакта')
    return
  }
  if (botId.value == null) {
    message.error('Выберите WhatsApp-бота')
    return
  }

  loading.value = true
  try {
    const result = await startWhatsappOutreach({
      phone: digits,
      full_name: name,
      bot_id: botId.value,
    })
    emit('started', result.chat_id)
    close()
  } catch (err) {
    const text =
      err instanceof AppError ? err.message : 'Не удалось открыть чат WhatsApp'
    message.error(text)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Написать в WhatsApp"
    style="max-width: 420px"
    @update:show="emit('update:show', $event)"
  >
    <p class="new-wa-chat__hint">
      Номер в международном формате, только цифры. Пример: <code>79001234567</code>
    </p>
    <NForm label-placement="top">
      <NFormItem label="Имя контакта" required>
        <NInput v-model:value="fullName" placeholder="Иван" :disabled="loading" />
      </NFormItem>
      <NFormItem label="Номер WhatsApp" required>
        <NInput
          v-model:value="phone"
          placeholder="79001234567"
          :disabled="loading"
          @keyup.enter="submit"
        />
      </NFormItem>
      <NFormItem label="Бот" required>
        <NSelect
          v-model:value="botId"
          :options="botOptions"
          placeholder="Выберите бота"
          :disabled="loading || botOptions.length === 0"
        />
      </NFormItem>
    </NForm>
    <p v-if="botOptions.length === 0" class="new-wa-chat__warn">
      Нет активных WhatsApp-ботов в вашем отделе.
    </p>
    <template #footer>
      <NButton quaternary :disabled="loading" @click="close">Отмена</NButton>
      <NButton
        type="primary"
        :loading="loading"
        :disabled="botOptions.length === 0"
        @click="submit"
      >
        Открыть чат
      </NButton>
    </template>
  </NModal>
</template>

<style scoped>
.new-wa-chat__hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--n-text-color-3);
}

.new-wa-chat__warn {
  margin: 0;
  font-size: 13px;
  color: var(--n-error-color);
}
</style>
