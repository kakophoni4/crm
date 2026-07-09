<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { NEmpty, NInput, NModal, NSpin, NTab, NTabs } from 'naive-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { ChatListItem } from '@/entities/chat/types'
import type { Contact } from '@/entities/contact/types'
import { globalSearch } from '@/features/search/api'
import type {
  GlobalSearchMessageItem,
  GlobalSearchResponse,
  GlobalSearchTab,
} from '@/features/search/types'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const router = useRouter()

const query = ref('')
const activeTab = ref<GlobalSearchTab>('contacts')
const loading = ref(false)
const error = ref<string | null>(null)
const results = ref<GlobalSearchResponse | null>(null)
const cursors = ref<Partial<Record<GlobalSearchTab, string | null>>>({})
const rateLimited = ref(false)
const inputRef = ref<InstanceType<typeof NInput> | null>(null)

const MIN_QUERY_LEN = 2

const tabLabels: { name: GlobalSearchTab; label: string }[] = [
  { name: 'contacts', label: 'Контакты' },
  { name: 'messages', label: 'Сообщения' },
  { name: 'chats', label: 'Чаты' },
]

const activeItems = computed(() => {
  if (!results.value) return []
  switch (activeTab.value) {
    case 'contacts':
      return results.value.contacts.items
    case 'messages':
      return results.value.messages.items
    case 'chats':
      return results.value.chats.items
    default:
      return []
  }
})

const showHint = computed(
  () => query.value.trim().length > 0 && query.value.trim().length < MIN_QUERY_LEN,
)

function close(): void {
  emit('update:show', false)
}

async function runSearch(q: string): Promise<void> {
  const trimmed = q.trim()
  if (trimmed.length < MIN_QUERY_LEN) {
    results.value = null
    error.value = null
    loading.value = false
    return
  }

  loading.value = true
  error.value = null
  rateLimited.value = false
  cursors.value = {}
  try {
    results.value = await globalSearch({ q: trimmed, limit_per_type: 10 })
    if (results.value) {
      cursors.value = {
        contacts: results.value.contacts.next_cursor,
        messages: results.value.messages.next_cursor,
        chats: results.value.chats.next_cursor,
      }
    }
  } catch (err) {
    results.value = null
    if (err instanceof AppError && err.status === 429) {
      rateLimited.value = true
      error.value = 'Слишком много запросов. Подождите минуту.'
    } else {
      error.value = err instanceof AppError ? err.message : 'Не удалось выполнить поиск'
    }
  } finally {
    loading.value = false
  }
}

const activeNextCursor = computed(() => cursors.value[activeTab.value] ?? null)

async function loadMore(): Promise<void> {
  const trimmed = query.value.trim()
  const cursor = activeNextCursor.value
  if (!results.value || !cursor || trimmed.length < MIN_QUERY_LEN) return

  loading.value = true
  try {
    const params: Parameters<typeof globalSearch>[0] = {
      q: trimmed,
      limit_per_type: 10,
    }
    if (activeTab.value === 'contacts') params.contacts_cursor = cursor
    if (activeTab.value === 'messages') params.messages_cursor = cursor
    if (activeTab.value === 'chats') params.chats_cursor = cursor

    const page = await globalSearch(params)
    const section = page[activeTab.value]
    const current = results.value[activeTab.value]
    results.value = {
      ...results.value,
      [activeTab.value]: {
        items: [...current.items, ...section.items],
        next_cursor: section.next_cursor,
      },
    }
    cursors.value[activeTab.value] = section.next_cursor
  } catch (err) {
    if (err instanceof AppError && err.status === 429) {
      rateLimited.value = true
      error.value = 'Слишком много запросов. Подождите минуту.'
    }
  } finally {
    loading.value = false
  }
}

watchDebounced(
  query,
  (value) => {
    void runSearch(value)
  },
  { debounce: 300 },
)

watch(
  () => props.show,
  async (visible) => {
    if (!visible) {
      query.value = ''
      results.value = null
      error.value = null
      activeTab.value = 'contacts'
      return
    }
    await nextTick()
    inputRef.value?.focus()
  },
)

function navigateToContact(contact: Contact): void {
  close()
  void router.push({ name: 'contact-detail', params: { id: contact.id } })
}

function navigateToChat(chatId: number): void {
  close()
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function onSelectContact(contact: Contact): void {
  navigateToContact(contact)
}

function onSelectMessage(item: GlobalSearchMessageItem): void {
  navigateToChat(item.chat_id)
}

function onSelectChat(chat: ChatListItem): void {
  navigateToChat(chat.id)
}

function resultLabel(item: Contact | GlobalSearchMessageItem | ChatListItem): string {
  if ('full_name' in item) return item.full_name
  if ('snippet' in item) return item.snippet.replace(/<[^>]+>/g, '')
  return item.contact_name
}

function resultMeta(item: Contact | GlobalSearchMessageItem | ChatListItem): string {
  if ('phone' in item) {
    const parts = [item.phone, item.telegram_username ? `@${item.telegram_username}` : null].filter(
      Boolean,
    )
    return parts.join(' · ') || `Контакт #${item.id}`
  }
  if ('snippet' in item) return `Чат #${item.chat_id}`
  return item.last_message_preview ?? `Чат #${item.id}`
}

function onResultClick(item: Contact | GlobalSearchMessageItem | ChatListItem): void {
  if ('full_name' in item) {
    onSelectContact(item)
    return
  }
  if ('snippet' in item) {
    onSelectMessage(item)
    return
  }
  onSelectChat(item)
}

function isMessageItem(
  item: Contact | GlobalSearchMessageItem | ChatListItem,
): item is GlobalSearchMessageItem {
  return 'snippet' in item
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Глобальный поиск"
    style="max-width: 560px"
    :trap-focus="true"
    :auto-focus="false"
    @update:show="emit('update:show', $event)"
    @after-leave="query = ''"
  >
    <div
      class="global-search-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Глобальный поиск"
    >
    <NInput
      ref="inputRef"
      v-model:value="query"
      clearable
      placeholder="Поиск контактов, сообщений и чатов…"
      aria-label="Строка глобального поиска"
      autocomplete="off"
      @keydown.esc.stop="close"
    />

    <NTabs v-model:value="activeTab" type="line" size="small" class="global-search-modal__tabs">
      <NTab v-for="tab in tabLabels" :key="tab.name" :name="tab.name" :tab="tab.label" />
    </NTabs>

    <p v-if="showHint" class="global-search-modal__hint">Введите минимум 2 символа</p>

    <NSpin :show="loading">
      <p v-if="error" class="global-search-modal__error" role="alert">{{ error }}</p>

      <ul
        v-else-if="activeItems.length"
        class="global-search-modal__results"
        role="listbox"
        :aria-label="`Результаты: ${tabLabels.find((t) => t.name === activeTab)?.label}`"
      >
        <li
          v-for="item in activeItems"
          :key="
            'full_name' in item
              ? `c-${item.id}`
              : 'snippet' in item
                ? `m-${item.message_id}`
                : `ch-${item.id}`
          "
          class="global-search-modal__result"
          role="option"
          tabindex="0"
          :aria-label="resultLabel(item)"
          @click="onResultClick(item)"
          @keydown.enter.prevent="onResultClick(item)"
        >
          <span
            v-if="isMessageItem(item)"
            class="global-search-modal__title"
            v-html="item.snippet"
          />
          <span v-else class="global-search-modal__title">{{ resultLabel(item) }}</span>
          <span class="global-search-modal__meta">{{ resultMeta(item) }}</span>
        </li>
      </ul>

      <NEmpty
        v-else-if="query.trim().length >= MIN_QUERY_LEN && !loading"
        description="Ничего не найдено"
      />

      <button
        v-if="activeNextCursor && !rateLimited"
        type="button"
        class="global-search-modal__more"
        :disabled="loading"
        @click="loadMore"
      >
        Загрузить ещё
      </button>
      <p v-if="rateLimited" class="global-search-modal__error" role="alert">
        Превышен лимит поиска. Повторите позже.
      </p>
    </NSpin>

    <p class="global-search-modal__shortcuts">
      <kbd>Ctrl</kbd>+<kbd>K</kbd> открыть · <kbd>Esc</kbd> закрыть
    </p>
    </div>
  </NModal>
</template>

<style scoped>
.global-search-modal__tabs {
  margin-top: 12px;
}

.global-search-modal__hint,
.global-search-modal__error {
  margin: 8px 0 0;
  font-size: 0.85rem;
}

.global-search-modal__error {
  color: var(--app-danger);
}

.global-search-modal__results {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  max-height: 320px;
  overflow-y: auto;
}

.global-search-modal__result {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
}

.global-search-modal__result:hover,
.global-search-modal__result:focus-visible {
  background: var(--app-surface-elevated, #f4f4f5);
  outline: none;
}

.global-search-modal__title {
  display: block;
  font-weight: 600;
}

.global-search-modal__title :deep(mark) {
  background: var(--app-accent-soft, #e8f3ff);
  color: inherit;
  padding: 0 2px;
  border-radius: 2px;
}

.global-search-modal__meta {
  display: block;
  margin-top: 2px;
  font-size: 0.8rem;
  opacity: 0.75;
}

.global-search-modal__shortcuts {
  margin: 12px 0 0;
  font-size: 0.75rem;
  opacity: 0.65;
}

.global-search-modal__more {
  margin-top: 10px;
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border, #e0e0e6);
  background: var(--app-surface, #fafafa);
  cursor: pointer;
}

.global-search-modal__shortcuts kbd {
  font-family: inherit;
  padding: 1px 4px;
  border-radius: var(--app-control-radius, 8px);
  border: 1px solid var(--app-border, #e0e0e6);
  background: var(--app-surface, #fafafa);
}
</style>
