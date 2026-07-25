<script setup lang="ts">

import {

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

  NVirtualList,

  useMessage,

} from 'naive-ui'

import { formatDistanceToNow } from 'date-fns'

import { ru } from 'date-fns/locale'

import { useWindowSize } from '@vueuse/core'
import { ArrowLeft, MessageSquare, X } from 'lucide-vue-next'

import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'



import type { BotListItem } from '@/entities/bot/types'
import type { ChatListItem, ChatListTab, ChatMessage } from '@/entities/chat/types'
import ContactOwnerBadge from '@/entities/contact/ContactOwnerBadge.vue'
import { listBots } from '@/features/bots/api'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { registerChatListSearchFocus } from '@/features/chats/chat-list-search-focus'
import { formatChatMessagePreview } from '@/features/chats/message-preview'
import { useChatsStore } from '@/features/chats/store'
import {
  chatListItemIsAnswered,
  chatListItemNeedsResponse,
  chatListItemStatusLabel,
  chatOwnerBadgeEscalated,
  chatOwnerBadgePending,
  filterLeadPipelineStatuses,
  filterOpenLeadPipelineStatuses,
  formatContactClientLabel,
  resolveTerminalStatusId,
} from '@/features/leads/mapping'
import type { StatusOption } from '@/features/leads/types'
import { useStatusesStore } from '@/features/statuses/store'

import { useChatNotificationsStore } from '@/features/chats/notifications-store'
import ChatsNotificationsPane from '@/widgets/chat/ChatsNotificationsPane.vue'

import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import ContactAvatar from '@/shared/ui/ContactAvatar.vue'

import { onChatsInvalidate } from '@/shared/lib/query-invalidation'
import { connectChatsRealtime } from '@/shared/realtime/chats-ws'
import { priorityPrefetchChat } from '@/features/chats/snapshot-cache'
import { connectLeadsRealtime } from '@/shared/realtime/leads-ws'

import { connectOwnershipRealtime } from '@/shared/realtime/ownership-ws'

import MessageInput from '@/widgets/chat/MessageInput.vue'

import MessageList from '@/widgets/chat/MessageList.vue'

import TakeoverBadge from '@/widgets/chat/TakeoverBadge.vue'

/** Heavy side panels / dialogs — load on first open, not with /chats TTI. */
const TransferCardDialog = defineAsyncComponent(
  () => import('@/features/contacts/transfer-card/TransferCardDialog.vue'),
)
const ChatDealSidePanel = defineAsyncComponent(
  () => import('@/widgets/chat/ChatDealSidePanel.vue'),
)
const ChatPaymentsSidePanel = defineAsyncComponent(
  () => import('@/widgets/chat/ChatPaymentsSidePanel.vue'),
)
const NewWhatsappChatDialog = defineAsyncComponent(
  () => import('@/widgets/chat/NewWhatsappChatDialog.vue'),
)



const CHATS_NARROW_BREAKPOINT = 1024
/** Fixed row height for NVirtualList (padding + avatar + owner + preview + meta + gap). */
const CHAT_LIST_ITEM_SIZE = 132
const CHAT_LIST_LOAD_MORE_PX = 240
const CHAT_LIST_LOAD_MORE_THROTTLE_MS = 500

const store = useChatsStore()
const notifications = useChatNotificationsStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { width } = useWindowSize()
const isNarrow = computed(() => width.value < CHATS_NARROW_BREAKPOINT)
const narrowPane = ref<'list' | 'chat'>('list')

const message = useMessage()
const chatListSearchRef = ref<InstanceType<typeof NInput> | null>(null)
const messageListRef = ref<{ scrollToBottomForced?: () => void } | null>(null)
const replyToMessage = ref<ChatMessage | null>(null)

const transferCardVisible = ref(false)
const transferInboxOpen = ref(false)
const newWhatsappChatVisible = ref(false)
const bots = ref<BotListItem[]>([])
const botsLoading = ref(false)
const pipelineStatuses = ref<StatusOption[]>([])
const openPipelineStatuses = ref<StatusOption[]>([])

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

const chatWorkflowLabel = computed(() => store.currentChat?.chat_label?.label?.trim() || null)

const contactClientLabel = computed(() =>
  formatContactClientLabel(store.currentChat?.contact_client_label),
)

type RightPaneTab = 'deal' | 'payments' | 'notifications'
const rightPaneTab = ref<RightPaneTab>('notifications')

/** Short labels always — fits list pane with WhatsApp action in one row. */
const listTabsForPane: { name: ChatListTab; label: string }[] = [
  { name: 'mine', label: 'Мои' },
  { name: 'group', label: 'Группа' },
  { name: 'needs_response', label: 'Ответ' },
]

function goToContact(): void {
  const contactId = store.currentChat?.contact_id
  if (contactId == null) return
  void router.push({ name: 'contact-detail', params: { id: contactId } })
}

const transferGroupId = computed(() => store.currentChat?.assigned_group_id ?? null)

const canTransferCard = computed(() => {
  const chat = store.currentChat
  const me = auth.user?.id
  if (chat == null || me == null || transferGroupId.value == null) return false
  if (auth.canForceCardOwner) return true
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

const transferGroupOptions = computed(() => {
  const chat = store.currentChat
  if (chat == null) return []
  const bot = chat.bot_id != null ? bots.value.find((item) => item.id === chat.bot_id) : null
  const ids =
    bot?.assigned_group_ids?.length
      ? bot.assigned_group_ids
      : chat.assigned_group_id != null
        ? [chat.assigned_group_id]
        : []
  return [...new Set(ids)].map((id) => ({
    label:
      lookupGroupName(id)?.trim() ||
      (id === chat.assigned_group_id ? chat.assigned_group_name?.trim() : '') ||
      `Группа #${id}`,
    value: id,
  }))
})

const fallbackOutboundNick = computed(() => {
  const chat = store.currentChat
  if (chat?.bot_id == null) return null
  const bot = bots.value.find((item) => item.id === chat.bot_id)
  return bot?.channel === 'telegram' ? 'TG Bot' : null
})

async function onCardTransferred(): Promise<void> {
  await store.fetchList()
  await store.refreshCurrentChatOwner()
}

function isHighlighted(chatId: number): boolean {

  return store.highlightedChatIds.has(chatId)

}



const relativeTimeCache = new Map<string, string>()
const relativeTimeTick = ref(0)
let relativeTimeRefreshTimer: ReturnType<typeof setInterval> | undefined
let chatListLoadMoreGuardUntil = 0
const chatVirtualListRef = ref<{ listElRef?: HTMLElement | null } | null>(null)
let chatListScrollEl: HTMLElement | null = null

function formatRelative(iso: string | null): string {
  if (!iso) return ''
  void relativeTimeTick.value
  const cached = relativeTimeCache.get(iso)
  if (cached !== undefined) return cached
  try {
    const formatted = formatDistanceToNow(new Date(iso), { addSuffix: true, locale: ru })
    relativeTimeCache.set(iso, formatted)
    return formatted
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

function maybeFetchMoreChats(): void {
  if (!store.listNextCursor || store.listLoading) return
  const now = Date.now()
  if (now < chatListLoadMoreGuardUntil) return
  chatListLoadMoreGuardUntil = now + CHAT_LIST_LOAD_MORE_THROTTLE_MS
  void store.fetchList(true)
}

function onChatListScroll(e: Event): void {
  const el = e.target as HTMLElement | null
  if (!el || typeof el.scrollTop !== 'number') return
  if (el.scrollHeight - el.scrollTop - el.clientHeight > CHAT_LIST_LOAD_MORE_PX) return
  maybeFetchMoreChats()
}

function unbindChatListScroll(): void {
  if (chatListScrollEl == null) return
  chatListScrollEl.removeEventListener('scroll', onChatListScroll)
  chatListScrollEl = null
}

function resolveChatListScrollEl(): HTMLElement | null {
  const raw = chatVirtualListRef.value?.listElRef as unknown
  if (raw instanceof HTMLElement) return raw
  if (raw != null && typeof raw === 'object' && 'value' in raw) {
    const nested = (raw as { value?: unknown }).value
    return nested instanceof HTMLElement ? nested : null
  }
  return null
}

async function bindChatListScroll(): Promise<void> {
  await nextTick()
  let el = resolveChatListScrollEl()
  if (el == null) {
    await nextTick()
    el = resolveChatListScrollEl()
  }
  if (el == null || el === chatListScrollEl) return
  unbindChatListScroll()
  chatListScrollEl = el
  el.addEventListener('scroll', onChatListScroll, { passive: true })
}

function chatBotLabel(chat: ChatListItem): string | null {
  const fromApi = chat.bot_name?.trim()
  if (fromApi) return fromApi
  if (chat.bot_id == null) return null
  return bots.value.find((item) => item.id === chat.bot_id)?.name?.trim() || null
}



async function onSend(
  text: string,
  attachments: { file_id: number }[],
  replyToMessageId: number | null,
): Promise<void> {

  try {

    await store.sendMessage(text, attachments, replyToMessageId)
    replyToMessage.value = null

  } catch (err) {

    const textErr = err instanceof AppError ? err.message : 'Не удалось отправить'

    message.error(textErr)

  }

}

function onReplyToMessage(message: ChatMessage): void {
  replyToMessage.value = message
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

function openChatFromQuery(): void {
  const rawChat = route.query.chatId
  const chatId = typeof rawChat === 'string' ? Number(rawChat) : NaN
  if (!Number.isFinite(chatId) || chatId <= 0) return
  void store.openChat(chatId).then(() => {
    if (isNarrow.value) narrowPane.value = 'chat'
    void router.replace({ name: 'chats', query: { chatId: String(chatId) } })
  })
}

function prefetchChatOnHover(chatId: number): void {
  priorityPrefetchChat(chatId)
}

function openChatMobile(chatId: number): void {
  void store.openChat(chatId).then(() => {
    nextTick(() => messageListRef.value?.scrollToBottomForced?.())
  })
  if (isNarrow.value) narrowPane.value = 'chat'
}

/** Double-click list row: open (or refocus) and always jump to latest messages. */
function onChatListDblClick(chatId: number): void {
  void store.openChat(chatId).then(() => {
    if (isNarrow.value) narrowPane.value = 'chat'
    nextTick(() => messageListRef.value?.scrollToBottomForced?.())
  })
}

function onWhatsappChatStarted(chatId: number): void {
  void store.fetchList()
  void store.openChat(chatId).then(() => {
    if (isNarrow.value) narrowPane.value = 'chat'
    void router.replace({ name: 'chats', query: { chatId: String(chatId) } })
  })
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
    replyToMessage.value = null
    if (chatId != null) {
      if (isNarrow.value) narrowPane.value = 'chat'
      rightPaneTab.value = 'deal'
    } else {
      rightPaneTab.value = 'notifications'
    }
  },
)

onMounted(() => {
  registerChatListSearchFocus(() => chatListSearchRef.value?.focus())
  // Instant UI from localStorage (list / messages / deals / payments), then revalidate.
  store.hydrateFromDisk()
  void ensureGroupDirectory()
  void store.fetchList()
  void loadBots()
  void connectChatsRealtime()
  void connectLeadsRealtime()

  void connectOwnershipRealtime()
  void notifications.ensureConnected()
  void loadLeadStatuses()

  stopInvalidate = onChatsInvalidate(() => {
    store.scheduleSilentListRefresh()
  })

  openChatFromQuery()

  relativeTimeRefreshTimer = setInterval(() => {
    relativeTimeCache.clear()
    relativeTimeTick.value += 1
  }, 60_000)
})

watch(
  () => route.query.chatId,
  () => {
    openChatFromQuery()
  },
)

watch(
  () => !store.listInitialLoading && store.displayListItems.length > 0,
  (ready) => {
    if (ready) void bindChatListScroll()
    else unbindChatListScroll()
  },
  { immediate: true },
)

onUnmounted(() => {
  registerChatListSearchFocus(null)
  stopInvalidate?.()
  unbindChatListScroll()
  if (relativeTimeRefreshTimer != null) {
    clearInterval(relativeTimeRefreshTimer)
    relativeTimeRefreshTimer = undefined
  }
})

</script>



<template>

  <section class="chats-page">

    <div
      class="chats-page__split"
      :class="{
        'chats-page__split--narrow': isNarrow,
        'chats-page__split--show-list': isNarrow && narrowPane === 'list',
        'chats-page__split--show-chat': isNarrow && narrowPane === 'chat',
        'chats-page__split--deal-open': Boolean(store.currentChat) && !isNarrow,
      }"
    >

      <aside class="chats-page__list-pane">

        <div class="chats-page__list-toolbar">
          <NTabs
            v-model:value="store.listTab"
            type="segment"
            size="small"
            class="chats-page__tabs"
            animated
          >
            <NTab v-for="tab in listTabsForPane" :key="tab.name" :name="tab.name" :tab="tab.label" />
          </NTabs>

          <div class="chats-page__list-actions">
            <NButton
              type="primary"
              size="small"
              class="chats-page__wa-btn"
              @click="newWhatsappChatVisible = true"
            >
              WhatsApp
            </NButton>
            <NButton
              v-if="isNarrow"
              quaternary
              size="small"
              @click="transferInboxOpen = true"
            >
              Увед.
              <template v-if="notifications.unreadCount">
                ({{ notifications.unreadCount }})
              </template>
            </NButton>
          </div>
        </div>



        <NSpace class="chats-page__filters" vertical :size="8">

          <NInput
            ref="chatListSearchRef"
            v-model:value="store.filters.q"
            clearable
            placeholder="Поиск по контакту…"
            aria-label="Поиск в списке чатов"
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
        </NSpace>

        <div v-if="store.listInitialLoading" class="chats-page__skeleton">
          <NSkeleton v-for="n in 6" :key="n" text :repeat="2" style="margin-bottom: 12px" />
        </div>

        <NSpin
          v-else
          class="chats-page__list-spin"
          :show="store.listLoading && store.listLoaded"
        >
          <NVirtualList
            v-if="store.displayListItems.length"
            ref="chatVirtualListRef"
            class="chats-page__list"
            :items="store.displayListItems"
            :item-size="CHAT_LIST_ITEM_SIZE"
            key-field="id"
          >
            <template #default="{ item: chat }">
              <div
                class="chats-page__list-item"
                :class="{
                  'chats-page__list-item--active': store.currentChatId === chat.id,
                  'chats-page__list-item--highlight':
                    !chatListItemIsAnswered(chat) && isHighlighted(chat.id),
                  'chats-page__list-item--needs-response':
                    !chatListItemIsAnswered(chat) &&
                    (store.needsResponseChatIds.has(chat.id) ||
                      chatListItemNeedsResponse(chat)),
                }"
                tabindex="0"
                @mouseenter="prefetchChatOnHover(chat.id)"
                @click="openChatMobile(chat.id)"
                @dblclick.prevent="onChatListDblClick(chat.id)"
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
                  :escalated="chatOwnerBadgeEscalated(chat)"
                  :pending="chatOwnerBadgePending(chat)"
                />
                <p class="chats-page__preview">
                  {{ formatChatMessagePreview(chat.last_message_preview) }}
                </p>
                <span class="chats-page__meta">{{ chatMetaLine(chat) }}</span>
              </div>
            </template>
          </NVirtualList>

          <div
            v-if="store.displayListItems.length && store.listNextCursor"
            class="chats-page__load-more"
          >
            <NButton
              block
              secondary
              :loading="store.listLoading"
              @click="maybeFetchMoreChats()"
            >
              Показать еще
            </NButton>
          </div>

          <NEmpty
            v-if="!store.displayListItems.length && store.listError"
            description="Ошибка загрузки"
          >
            <template #extra>{{ store.listError }}</template>
          </NEmpty>
          <NEmpty v-else-if="!store.displayListItems.length" description="Нет чатов по фильтрам" />

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

              <button
                type="button"
                class="chats-page__contact-link"
                @click="goToContact"
              >
                <ContactAvatar
                  :contact-id="store.currentChat.contact_id"
                  :full-name="store.currentChat.contact_name"
                  :size="40"
                />
              </button>

              <div class="chats-page__chat-identity">

                <button type="button" class="chats-page__contact-name" @click="goToContact">
                  <h2>{{ store.currentChat.contact_name }}</h2>
                </button>

                <div v-if="store.currentChat" class="chats-page__chat-meta">
                  <ContactOwnerBadge
                    compact
                    :owner-full-name="store.currentChat.card_owner_full_name"
                    :owner-user-id="store.currentChat.card_owner_user_id"
                    :escalated="chatOwnerBadgeEscalated(store.currentChat)"
                    :pending="chatOwnerBadgePending(store.currentChat)"
                  />
                  <NTag
                    v-if="chatBotLabel(store.currentChat)"
                    size="small"
                    type="success"
                    :bordered="false"
                  >
                    {{ chatBotLabel(store.currentChat) }}
                  </NTag>
                  <NTag v-if="store.currentChat.contact_illiquid" size="small" type="warning" :bordered="false">
                    Неликвидный
                  </NTag>
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

          </header>



          <TakeoverBadge

            :takeover="store.activeTakeover"

            :chat-id="store.currentChatId"

            @released="onTakeoverReleased"

          />

          <MessageList
            ref="messageListRef"
            :key="store.currentChatId ?? 0"
            :messages="store.messages"
            :loading="store.messagesLoading"
            :loading-older="store.loadingOlderMessages"
            :has-more="Boolean(store.messagesNextCursor)"
            :chat-id="store.currentChatId"
            :contact-id="store.currentChat.contact_id"
            :contact-name="store.currentChat.contact_name"
            :fallback-outbound-nick="fallbackOutboundNick"
            @load-older="store.loadOlderMessages()"
            @reply="onReplyToMessage"
          />



          <MessageInput
            :disabled="store.isInputBlocked"
            :department-id="store.currentChat.assigned_department_id"
            :group-id="store.currentChat.assigned_group_id ?? store.currentChat.card_owner_group_id"
            :chat-id="store.currentChat.id"
            :reply-to="replyToMessage"
            @cancel-reply="replyToMessage = null"
            @send="onSend"
          />

        </template>



        <div v-else class="chats-page__placeholder">

          <MessageSquare :size="48" stroke-width="1.25" />

          <p>Выберите чат из списка</p>

        </div>

      </main>

      <aside v-if="!isNarrow" class="chats-page__inbox-pane">
        <NTabs
          v-if="store.currentChat"
          v-model:value="rightPaneTab"
          type="line"
          size="small"
          class="chats-page__right-tabs"
        >
          <NTab name="deal" tab="Сделки" />
          <NTab name="payments" tab="Оплаты клиента" />
          <NTab
            name="notifications"
            :tab="
              notifications.unreadCount
                ? `Уведомления (${notifications.unreadCount})`
                : 'Уведомления'
            "
          />
        </NTabs>
        <ChatDealSidePanel
          v-if="store.currentChat && rightPaneTab === 'deal'"
          :key="`deal-${store.currentChatId}`"
          :chat="store.currentChat"
          :bots="bots"
          :lead-status-options="leadStatusOptions"
          :won-status-id="wonStatusId"
          :lost-status-id="lostStatusId"
        />
        <ChatPaymentsSidePanel
          v-else-if="store.currentChat && rightPaneTab === 'payments'"
          :key="`pay-${store.currentChatId}`"
          :chat="store.currentChat"
        />
        <ChatsNotificationsPane
          v-else
          embedded
          :hide-title="!!store.currentChat"
        />
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
        <NButton
          quaternary
          circle
          size="small"
          class="chats-page__inbox-close"
          aria-label="Закрыть"
          @click="transferInboxOpen = false"
        >
          <X :size="18" />
        </NButton>
        <ChatsNotificationsPane embedded />
      </aside>
    </div>



    <NewWhatsappChatDialog
      v-model:show="newWhatsappChatVisible"
      :bots="bots"
      @started="onWhatsappChatStarted"
    />

    <TransferCardDialog

      v-model:show="transferCardVisible"

      :contact-id="store.currentChat?.contact_id ?? null"

      :group-id="transferGroupId"

      :group-options="transferGroupOptions"

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
  height: calc(100dvh - var(--app-topbar-height));
  max-height: calc(100dvh - var(--app-topbar-height));
  min-height: 480px;
  overflow: hidden;
  /* Чат занимает всю область контента: гасим внешние отступы layout (24px). */
  margin: calc(-1 * var(--app-content-padding));
}

.chats-page__list-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.chats-page__list-toolbar .chats-page__tabs {
  flex: 1 1 auto;
  min-width: 0;
  margin-bottom: 0;
}

.chats-page__list-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
}

.chats-page__wa-btn {
  white-space: nowrap;
}

.chats-page__tabs {
  margin-bottom: 0;
}

.chats-page__tabs :deep(.n-tabs-nav) {
  width: 100%;
}

.chats-page__tabs :deep(.n-tabs-rail),
.chats-page__tabs :deep(.n-tabs-wrapper) {
  width: 100%;
}

.chats-page__tabs :deep(.n-tabs-tab) {
  flex: 1 1 0;
  justify-content: center;
  font-size: 0.8rem;
  padding-left: 4px;
  padding-right: 4px;
  white-space: nowrap;
}

.chats-page__tabs :deep(.n-tabs-tab .n-tabs-tab__label) {
  overflow: hidden;
  text-overflow: ellipsis;
}



.chats-page__split {

  flex: 1;

  display: grid;

  grid-template-columns: minmax(260px, 320px) 1fr minmax(320px, 360px);

  gap: 0;

  border: none;

  border-radius: 0;

  overflow: hidden;

  min-height: 0;

}

.chats-page__split--deal-open {
  grid-template-columns: minmax(240px, 280px) 1fr minmax(340px, 400px);
}


.chats-page__contact-link,
.chats-page__contact-name {
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
  color: inherit;
}

.chats-page__contact-name h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1.25;
}

.chats-page__contact-link:hover,
.chats-page__contact-name:hover {
  opacity: 0.85;
}

.chats-page__list-pane {

  display: flex;

  flex-direction: column;

  border-right: 1px solid var(--app-border);

  padding: 12px;

  overflow: hidden;

  min-height: 0;

  background: var(--app-surface);

}



.chats-page__filters {

  margin-bottom: 12px;

  flex-shrink: 0;

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
  flex-shrink: 0;
}

.chats-page__list-spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.chats-page__list-spin :deep(.n-spin-container),
.chats-page__list-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chats-page__list {
  flex: 1;
  min-height: 0;
  height: 100%;
  margin: 0;
  padding: 0;
}

.chats-page__load-more {
  flex-shrink: 0;
  padding: 8px 0 4px;
}



.chats-page__list-item {

  box-sizing: border-box;

  /* Keep in sync with CHAT_LIST_ITEM_SIZE (height + margin-bottom). */
  height: 128px;

  padding: 10px 12px;

  border-radius: 8px;

  cursor: pointer;

  margin-bottom: 4px;

  overflow: hidden;

  transition: background 0.15s;

  display: flex;

  flex-direction: column;

  justify-content: flex-start;

}



.chats-page__list-item:hover {

  background: var(--app-surface-elevated);

}



.chats-page__list-item--active {

  background: var(--app-accent-soft);

}



.chats-page__list-item--highlight,

.chats-page__list-item--needs-response {

  box-shadow: inset 3px 0 0 var(--app-accent);

}



.chats-page__list-item--needs-response {

  box-shadow: inset 3px 0 0 var(--app-danger);

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

  margin-top: 2px;

  font-size: 0.75rem;

  line-height: 1.25;

  opacity: 0.65;

  white-space: nowrap;

  overflow: hidden;

  text-overflow: ellipsis;

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

  padding: 0;

  overflow: hidden;

  display: flex;

  flex-direction: column;

  min-height: 0;

  background: var(--app-surface);

}

.chats-page__right-tabs {
  flex-shrink: 0;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--app-border);
}

.chats-page__inbox-pane > :not(.chats-page__right-tabs) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
  gap: 4px;
  margin-top: 4px;
  max-width: 100%;
}

.chats-page__chat-meta :deep(.n-tag) {
  max-width: 100%;
}

.chats-page__chat-meta :deep(.n-tag__content) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}



.chats-page__chat-header h2 {
  margin: 0;
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
  background: var(--app-surface-elevated);
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
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--app-text) 15%, transparent);
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
    display: flex;
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
  display: flex;
  flex-direction: column;
  width: min(360px, 92vw);
  height: 100%;
  background: var(--app-surface);
  padding: 12px;
  overflow: hidden;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
}

.chats-page__inbox-close {
  flex-shrink: 0;
  margin: 0 0 8px auto;
  display: flex;
}

</style>
