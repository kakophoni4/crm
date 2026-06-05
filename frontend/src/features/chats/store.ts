import { watchDebounced } from '@vueuse/core'
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import type {
  ChatDetail,
  ChatListItem,
  ChatListParams,
  ChatListSort,
  ChatListTab,
  ChatMessage,
  CurrentLeadSnippet,
  MessageScope,
  TakeoverState,
} from '@/entities/chat/types'
import {
  closeLead as closeLeadApi,
  patchLead as patchLeadApi,
} from '@/features/leads/api'
import type { GroupOwnershipItem } from '@/entities/contact/types'
import * as chatsApi from '@/features/chats/api'
import {
  applyOwnershipToChat,
  enrichMessagesWithReplyAudit,
  ownershipKey,
} from '@/features/chats/ownership-enrich'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { useAuthStore } from '@/shared/store/auth'

export const useChatsStore = defineStore('chats', () => {
  const auth = useAuthStore()

  const listItems = ref<ChatListItem[]>([])
  const listLoading = ref(false)
  const listLoaded = ref(false)
  const listError = ref<string | null>(null)
  const listNextCursor = ref<string | null>(null)
  const highlightedChatIds = ref<Set<number>>(new Set())

  const currentChatId = ref<number | null>(null)
  const currentChat = ref<ChatDetail | null>(null)
  const messages = ref<ChatMessage[]>([])
  const messagesLoading = ref(false)
  const messagesNextCursor = ref<string | null>(null)
  const messageScope = ref<MessageScope>('all')
  const leadClosedBanner = ref(false)

  const typingByChatId = ref<Record<number, boolean>>({})
  const takeoverByChatId = ref<Record<number, TakeoverState>>({})

  const listTab = ref<ChatListTab>('mine')
  const needsResponseChatIds = ref<Set<number>>(new Set())
  const ownershipByKey = ref<Record<string, GroupOwnershipItem>>({})

  const filters = ref({
    q: '',
    chatStatusId: null as number | null,
    botId: null as number | null,
    unreadOnly: false,
    leadStatusId: null as number | null,
    leadOpenOnly: false,
    sort: 'last_message_at_desc' as ChatListSort,
  })

  const closingLead = ref(false)
  const updatingLeadStatus = ref(false)

  /** Bumps on each openChat(); stale async results are ignored. */
  let openChatSeq = 0

  function isActiveChat(chatId: number, seq: number): boolean {
    return seq === openChatSeq && currentChatId.value === chatId
  }

  const activeTakeover = computed(() => {
    if (currentChatId.value == null) return null
    return takeoverByChatId.value[currentChatId.value] ?? null
  })

  const isInputBlocked = computed(() => {
    const takeover = activeTakeover.value
    if (!takeover) return false
    const me = auth.user?.id
    if (!me) return false
    return takeover.senior_user_id !== me
  })

  const isSenior = computed(
    () => auth.user?.role === 'senior' || auth.user?.role === 'admin',
  )

  const listInitialLoading = computed(() => listLoading.value && !listLoaded.value)

  const displayListItems = computed(() => listItems.value)

  function buildListQuery(append: boolean): ChatListParams {
    const me = auth.user?.id
    const params: ChatListParams = {
      q: filters.value.q.trim() || undefined,
      status_id: filters.value.chatStatusId ?? undefined,
      bot_id: filters.value.botId ?? undefined,
      unread_only: filters.value.unreadOnly || undefined,
      sort: filters.value.sort,
      cursor: append ? (listNextCursor.value ?? undefined) : undefined,
      limit: 50,
    }
    if (listTab.value === 'mine' && me != null) {
      params.card_owner_user_id = me
    }
    if (listTab.value === 'needs_response') {
      params.needs_reply = true
    }
    if (filters.value.leadStatusId != null) {
      params.lead_status_id = filters.value.leadStatusId
    }
    if (filters.value.leadOpenOnly) {
      params.lead_open_only = true
    }
    return params
  }

  function patchChatLead(chatId: number, lead: CurrentLeadSnippet | null): void {
    const idx = listItems.value.findIndex((c) => c.id === chatId)
    if (idx >= 0) {
      listItems.value[idx] = { ...listItems.value[idx], current_lead: lead }
    }
    if (currentChatId.value === chatId && currentChat.value) {
      currentChat.value = { ...currentChat.value, current_lead: lead }
    }
  }

  async function refreshCurrentChatOwner(): Promise<void> {
    const chatId = currentChatId.value
    if (chatId == null) return
    try {
      const detail = await chatsApi.getChat(chatId)
      if (currentChatId.value !== chatId) return
      currentChat.value = detail
      const idx = listItems.value.findIndex((c) => c.id === chatId)
      if (idx >= 0) {
        listItems.value[idx] = {
          ...listItems.value[idx],
          card_owner_user_id: detail.card_owner_user_id,
          card_owner_full_name: detail.card_owner_full_name,
        }
      }
    } catch {
      /* best-effort */
    }
  }

  async function refreshChatLead(chatId: number): Promise<void> {
    try {
      const detail = await chatsApi.getChat(chatId)
      patchChatLead(chatId, detail.current_lead ?? null)
      if (detail.chat_label) {
        const idx = listItems.value.findIndex((c) => c.id === chatId)
        if (idx >= 0) {
          listItems.value[idx] = { ...listItems.value[idx], chat_label: detail.chat_label }
        }
        if (currentChatId.value === chatId && currentChat.value) {
          currentChat.value = {
            ...currentChat.value,
            chat_label: detail.chat_label,
          }
        }
      }
    } catch {
      /* best-effort */
    }
  }

  async function handleLeadEvent(
    topic: string,
    payload: Record<string, unknown>,
  ): Promise<void> {
    const chatId = Number(payload.chat_id)
    if (topic === 'lead.closed') {
      if (Number.isFinite(chatId)) {
        patchChatLead(chatId, null)
      }
      const leadId = Number(payload.lead_id)
      if (
        currentChat.value?.current_lead?.id === leadId ||
        (Number.isFinite(chatId) && currentChatId.value === chatId)
      ) {
        if (Number.isFinite(chatId)) {
          await refreshChatLead(chatId)
        } else {
          patchChatLead(currentChatId.value!, null)
        }
      }
      return
    }

    if (Number.isFinite(chatId)) {
      await refreshChatLead(chatId)
      return
    }

    const leadId = Number(payload.lead_id)
    if (currentChat.value?.current_lead?.id === leadId && currentChatId.value != null) {
      await refreshChatLead(currentChatId.value)
    }
  }

  async function closeCurrentLead(statusId: number): Promise<void> {
    const lead = currentChat.value?.current_lead
    if (!lead || lead.closed_at != null || closingLead.value) return
    closingLead.value = true
    try {
      await closeLeadApi(lead.id, statusId)
      if (currentChatId.value != null) {
        patchChatLead(currentChatId.value, null)
        await refreshChatLead(currentChatId.value)
        leadClosedBanner.value = true
        messageScope.value = 'all'
        await reloadMessages()
      }
    } finally {
      closingLead.value = false
    }
  }

  async function updateChatLabel(statusId: number): Promise<void> {
    if (currentChatId.value == null) return
    const detail = await chatsApi.patchChatStatusId(currentChatId.value, statusId)
    currentChat.value = detail
    const idx = listItems.value.findIndex((c) => c.id === currentChatId.value)
    if (idx >= 0) {
      listItems.value[idx] = { ...listItems.value[idx], chat_label: detail.chat_label }
    }
  }

  async function updateCurrentLeadStatus(statusId: number): Promise<void> {
    const lead = currentChat.value?.current_lead
    if (!lead || lead.closed_at != null || updatingLeadStatus.value) return
    updatingLeadStatus.value = true
    try {
      const updated = await patchLeadApi(lead.id, { status_id: statusId })
      const nextStatusId = updated.status_id ?? statusId
      const snippet: CurrentLeadSnippet = {
        id: updated.id,
        status_id: nextStatusId,
        label: updated.status_label ?? lead.label,
        comment: updated.comment ?? lead.comment ?? null,
        closed_at: updated.closed_at,
      }
      if (currentChatId.value != null) {
        patchChatLead(currentChatId.value, snippet)
      }
    } finally {
      updatingLeadStatus.value = false
    }
  }

  async function updateCurrentLeadComment(comment: string | null): Promise<void> {
    const lead = currentChat.value?.current_lead
    if (!lead || lead.closed_at != null) return
    const updated = await patchLeadApi(lead.id, { comment })
    const snippet: CurrentLeadSnippet = {
      id: updated.id,
      status_id: updated.status_id ?? lead.status_id,
      label: updated.status_label ?? lead.label,
      comment: updated.comment ?? null,
      closed_at: updated.closed_at,
    }
    if (currentChatId.value != null) {
      patchChatLead(currentChatId.value, snippet)
    }
  }

  function patchOwnershipFromPayload(payload: Record<string, unknown>): void {
    const contactId = Number(payload.contact_id)
    const groupId = Number(payload.group_id)
    if (!Number.isFinite(contactId) || !Number.isFinite(groupId)) return

    const key = ownershipKey(contactId, groupId)
    const prev = ownershipByKey.value[key]
    const ownerRaw =
      payload.owner_user_id ?? payload.to_user_id ?? payload.new_owner_user_id ?? payload.new_owner
    const ownerId = ownerRaw != null ? Number(ownerRaw) : (prev?.owner_user_id ?? null)
    const resolvedOwnerId = Number.isFinite(ownerId as number) ? (ownerId as number) : null
    const prevOwnerId = prev?.owner_user_id ?? null
    let ownerFullName: string | null = null
    if (typeof payload.owner_full_name === 'string') {
      ownerFullName = payload.owner_full_name.trim() || null
    } else if (resolvedOwnerId != null && resolvedOwnerId === prevOwnerId) {
      ownerFullName = prev?.owner_full_name ?? null
    }

    const ownership: GroupOwnershipItem = {
      group_id: groupId,
      group_name: prev?.group_name ?? lookupGroupName(groupId) ?? '',
      owner_user_id: resolvedOwnerId,
      owner_full_name: ownerFullName,
      pending_inbound_at: prev?.pending_inbound_at ?? null,
      escalated_at: prev?.escalated_at ?? null,
    }

    ownershipByKey.value = {
      ...ownershipByKey.value,
      [key]: ownership,
    }

    listItems.value = listItems.value.map((chat) => {
      if (chat.contact_id !== contactId || chat.assigned_group_id !== groupId) return chat
      return applyOwnershipToChat(chat, ownership)
    })

    if (
      currentChat.value &&
      currentChat.value.contact_id === contactId &&
      currentChat.value.assigned_group_id === groupId
    ) {
      currentChat.value = {
        ...currentChat.value,
        ...applyOwnershipToChat(currentChat.value, ownership),
      }
    }
  }

  function enrichListWithOwnership(items: ChatListItem[]): ChatListItem[] {
    return items.map((chat) => {
      if (chat.assigned_group_id == null) return chat
      const key = ownershipKey(chat.contact_id, chat.assigned_group_id)
      return applyOwnershipToChat(chat, ownershipByKey.value[key])
    })
  }

  function bumpChatInList(
    chatId: number,
    patch: Partial<ChatListItem>,
    highlight = true,
  ): void {
    const idx = listItems.value.findIndex((c) => c.id === chatId)
    if (idx >= 0) {
      listItems.value[idx] = { ...listItems.value[idx], ...patch }
      const [item] = listItems.value.splice(idx, 1)
      listItems.value.unshift(item)
    }
    if (highlight) {
      const next = new Set(highlightedChatIds.value)
      next.add(chatId)
      highlightedChatIds.value = next
    }
  }

  function clearHighlight(chatId: number): void {
    if (!highlightedChatIds.value.has(chatId)) return
    const next = new Set(highlightedChatIds.value)
    next.delete(chatId)
    highlightedChatIds.value = next
  }

  function enrichWithGroupNames(items: ChatListItem[]): ChatListItem[] {
    return items.map((chat) => {
      if (chat.assigned_group_id == null) return chat
      const name =
        chat.assigned_group_name?.trim() ||
        lookupGroupName(chat.assigned_group_id)?.trim()
      if (!name) return chat
      return { ...chat, assigned_group_name: name }
    })
  }

  async function fetchList(append = false): Promise<void> {
    listLoading.value = true
    if (!append) listError.value = null
    try {
      await ensureGroupDirectory()
      const data = await chatsApi.listChats(buildListQuery(append))
      const items = enrichWithGroupNames(data.items)
      listItems.value = enrichListWithOwnership(append ? [...listItems.value, ...items] : items)
      listNextCursor.value = data.next_cursor
    } catch (err) {
      if (!append) {
        listItems.value = []
        listError.value = err instanceof Error ? err.message : 'Не удалось загрузить чаты'
      }
      throw err
    } finally {
      listLoading.value = false
      listLoaded.value = true
    }
  }

  watchDebounced(
    () => filters.value.q,
    () => {
      void fetchList()
    },
    { debounce: 300 },
  )

  watch(
    () =>
      [
        listTab.value,
        filters.value.chatStatusId,
        filters.value.botId,
        filters.value.unreadOnly,
        filters.value.leadStatusId,
        filters.value.leadOpenOnly,
        filters.value.sort,
      ] as const,
    () => {
      void fetchList()
    },
  )

  function resolveMessagesLeadId(): number | undefined {
    if (messageScope.value !== 'current_lead') return undefined
    return currentChat.value?.current_lead?.id
  }

  async function reloadMessages(): Promise<void> {
    if (!currentChatId.value || !currentChat.value) return
    const chatId = currentChatId.value
    const seq = openChatSeq
    const leadId = resolveMessagesLeadId()
    if (messageScope.value === 'current_lead' && leadId == null) {
      messages.value = []
      messagesNextCursor.value = null
      return
    }
    messagesLoading.value = true
    try {
      const msgs = await chatsApi.listMessages(chatId, {
        limit: 50,
        lead_id: leadId,
      })
      if (!isActiveChat(chatId, seq)) return
      messages.value = await enrichMessagesWithReplyAudit(
        currentChat.value.contact_id,
        currentChat.value.assigned_group_id,
        msgs.items,
      )
      if (!isActiveChat(chatId, seq)) return
      messagesNextCursor.value = msgs.next_cursor
    } finally {
      if (isActiveChat(chatId, seq)) {
        messagesLoading.value = false
      }
    }
  }

  async function setMessageScope(scope: MessageScope): Promise<void> {
    if (messageScope.value === scope) return
    if (scope === 'current_lead') {
      leadClosedBanner.value = false
    }
    messageScope.value = scope
    await reloadMessages()
  }

  async function openChat(chatId: number): Promise<void> {
    const seq = ++openChatSeq
    leadClosedBanner.value = false
    currentChatId.value = chatId
    clearHighlight(chatId)
    messageScope.value = 'all'

    const cached = listItems.value.find((c) => c.id === chatId)
    currentChat.value = cached ? ({ ...cached } as ChatDetail) : null
    messages.value = []
    messagesNextCursor.value = null
    messagesLoading.value = true

    try {
      void ensureGroupDirectory()
      const detail = await chatsApi.getChat(chatId)
      if (!isActiveChat(chatId, seq)) return

      const groupName =
        detail.assigned_group_name?.trim() ||
        (detail.assigned_group_id != null
          ? lookupGroupName(detail.assigned_group_id)?.trim()
          : undefined)
      currentChat.value =
        groupName && !detail.assigned_group_name
          ? { ...detail, assigned_group_name: groupName }
          : detail

      const leadId =
        messageScope.value === 'current_lead' ? detail.current_lead?.id : undefined
      if (messageScope.value === 'current_lead' && leadId == null) {
        messages.value = []
        messagesNextCursor.value = null
      } else {
        const msgs = await chatsApi.listMessages(chatId, {
          limit: 50,
          lead_id: leadId,
        })
        if (!isActiveChat(chatId, seq)) return

        messages.value = await enrichMessagesWithReplyAudit(
          detail.contact_id,
          detail.assigned_group_id,
          msgs.items,
        )
        if (!isActiveChat(chatId, seq)) return
        messagesNextCursor.value = msgs.next_cursor
      }

      void chatsApi.markChatRead(chatId).catch(() => undefined)
      const idx = listItems.value.findIndex((c) => c.id === chatId)
      if (idx >= 0) {
        listItems.value[idx] = {
          ...listItems.value[idx],
          unread_for_me: false,
        }
      }
    } finally {
      if (isActiveChat(chatId, seq)) {
        messagesLoading.value = false
      }
    }
  }

  function closeChat(): void {
    openChatSeq += 1
    currentChatId.value = null
    currentChat.value = null
    messages.value = []
    messagesNextCursor.value = null
    messageScope.value = 'all'
  }

  async function loadOlderMessages(): Promise<void> {
    if (!currentChatId.value || !messagesNextCursor.value || !currentChat.value) return
    const chatId = currentChatId.value
    const seq = openChatSeq
    const data = await chatsApi.listMessages(chatId, {
      cursor: messagesNextCursor.value,
      limit: 50,
      lead_id: resolveMessagesLeadId(),
    })
    if (!isActiveChat(chatId, seq) || !currentChat.value) return
    const older = await enrichMessagesWithReplyAudit(
      currentChat.value.contact_id,
      currentChat.value.assigned_group_id,
      data.items,
    )
    if (!isActiveChat(chatId, seq)) return
    messages.value = [...older, ...messages.value]
    messagesNextCursor.value = data.next_cursor
  }

  async function sendMessage(
    text: string,
    attachments: { file_id: number; name?: string; mime?: string }[] = [],
  ): Promise<void> {
    if (!currentChatId.value || isInputBlocked.value) return

    const chatId = currentChatId.value
    const clientKey = crypto.randomUUID()
    const optimistic: ChatMessage = {
      id: -Date.now(),
      chat_id: chatId,
      direction: 'outbound',
      kind: 'text',
      text,
      attachments: attachments.map((a) => ({ file_id: a.file_id, status: 'queued' })),
      sender_user_id: auth.user?.id ?? null,
      reply_to_message_id: null,
      created_at: new Date().toISOString(),
      idempotency_key: clientKey,
      _optimistic: true,
      _clientKey: clientKey,
    }
    messages.value.push(optimistic)
    bumpChatInList(chatId, {
      last_message_preview: text.slice(0, 200),
      last_message_at: optimistic.created_at,
    }, false)

    try {
      const saved = await chatsApi.sendMessage(chatId, {
        text: text || undefined,
        attachments: attachments.map((a) => ({
          file_id: a.file_id,
          name: a.name,
          mime: a.mime,
        })),
        idempotency_key: clientKey,
      })
      const idx = messages.value.findIndex((m) => m._clientKey === clientKey)
      if (idx >= 0) {
        messages.value[idx] = { ...saved, _clientKey: clientKey }
      } else {
        messages.value.push(saved)
      }
    } catch (err) {
      const idx = messages.value.findIndex((m) => m._clientKey === clientKey)
      if (idx >= 0) {
        messages.value[idx] = {
          ...messages.value[idx],
          _failed: true,
        }
      }
      throw err
    }
  }

  async function handleInboundMessage(payload: Record<string, unknown>): Promise<void> {
    const chatId = Number(payload.chat_id)
    const messageId = Number(payload.message_id)
    if (!Number.isFinite(chatId)) return

    bumpChatInList(chatId, {
      unread_for_me: currentChatId.value !== chatId,
      last_message_at: new Date().toISOString(),
    })

    if (currentChatId.value === chatId) {
      await refreshOpenChatMessages(chatId, messageId)
    }
  }

  async function handleAttachmentReady(payload: Record<string, unknown>): Promise<void> {
    const chatId = Number(payload.chat_id)
    const messageId = Number(payload.message_id)
    if (!Number.isFinite(chatId) || currentChatId.value !== chatId) return
    await refreshOpenChatMessages(chatId, messageId)
  }

  async function refreshOpenChatMessages(chatId: number, messageId: number): Promise<void> {
    const seq = openChatSeq
    if (!isActiveChat(chatId, seq) || !currentChat.value) return
    const leadId = resolveMessagesLeadId()
    try {
      const msgs = await chatsApi.listMessages(chatId, {
        limit: 50,
        lead_id: leadId,
      })
      if (!isActiveChat(chatId, seq) || !currentChat.value) return

      const enriched = await enrichMessagesWithReplyAudit(
        currentChat.value.contact_id,
        currentChat.value.assigned_group_id,
        msgs.items,
      )
      if (!isActiveChat(chatId, seq)) return

      const existingIds = new Set(messages.value.map((m) => m.id))
      const fresh = enriched.filter((m) => !existingIds.has(m.id))
      if (fresh.length > 0) {
        messages.value = [...messages.value, ...fresh]
        return
      }
      const updated = enriched.find((m) => m.id === messageId)
      if (updated) {
        const idx = messages.value.findIndex((m) => m.id === messageId)
        if (idx >= 0) {
          messages.value[idx] = updated
          messages.value = [...messages.value]
          return
        }
      }
      if (!existingIds.has(messageId) && messageId > 0) {
        const fallback = enriched.find((m) => m.id === messageId) ?? enriched.slice(-1)[0]
        if (fallback) {
          messages.value = [...messages.value, fallback]
        }
      }
    } catch {
      /* list refresh is best-effort */
    }
  }

  function handleTakeoverStarted(payload: Record<string, unknown>): void {
    const chatId = Number(payload.chat_id)
    const seniorUserId = Number(payload.senior_user_id)
    if (!Number.isFinite(chatId) || !Number.isFinite(seniorUserId)) return
    takeoverByChatId.value = {
      ...takeoverByChatId.value,
      [chatId]: {
        chat_id: chatId,
        senior_user_id: seniorUserId,
        takeover_id: Number(payload.takeover_id) || undefined,
      },
    }
  }

  function handleTakeoverReleased(payload: Record<string, unknown>): void {
    const chatId = Number(payload.chat_id)
    if (!Number.isFinite(chatId)) return
    const next = { ...takeoverByChatId.value }
    delete next[chatId]
    takeoverByChatId.value = next
  }

  function setTyping(chatId: number, active: boolean): void {
    typingByChatId.value = { ...typingByChatId.value, [chatId]: active }
  }

  function handleOwnershipChanged(payload: Record<string, unknown>): void {
    patchOwnershipFromPayload(payload)
  }

  function handleEscalationOwnerNotify(payload: Record<string, unknown>): void {
    const chatId = Number(payload.chat_id)
    if (!Number.isFinite(chatId)) return
    bumpChatInList(chatId, { needs_response: true }, true)
  }

  function handleEscalationGroupNotify(payload: Record<string, unknown>): void {
    const chatId = Number(payload.chat_id)
    if (!Number.isFinite(chatId)) return
    const next = new Set(needsResponseChatIds.value)
    next.add(chatId)
    needsResponseChatIds.value = next
    bumpChatInList(
      chatId,
      { needs_response: true, escalated_at: new Date().toISOString() },
      true,
    )
  }

  function handleMessageOnBehalf(payload: Record<string, unknown>): void {
    const chatId = Number(payload.chat_id)
    const messageId = Number(payload.message_id)
    if (!Number.isFinite(chatId) || !Number.isFinite(messageId)) return
    if (currentChatId.value !== chatId) return

    const idx = messages.value.findIndex((m) => m.id === messageId)
    if (idx < 0) return

    messages.value[idx] = {
      ...messages.value[idx],
      is_on_behalf: true,
      author_user_id: Number(payload.author_user_id) || messages.value[idx].author_user_id,
      card_owner_user_id:
        Number(payload.card_owner_user_id) || messages.value[idx].card_owner_user_id,
    }
  }

  function setContactOwnership(contactId: number, items: GroupOwnershipItem[]): void {
    const next = { ...ownershipByKey.value }
    for (const item of items) {
      next[ownershipKey(contactId, item.group_id)] = item
    }
    ownershipByKey.value = next
    listItems.value = enrichListWithOwnership(listItems.value)
  }

  return {
    listItems,
    listLoading,
    listLoaded,
    listError,
    listInitialLoading,
    listNextCursor,
    highlightedChatIds,
    currentChatId,
    currentChat,
    messages,
    messagesLoading,
    messagesNextCursor,
    messageScope,
    leadClosedBanner,
    setMessageScope,
    reloadMessages,
    typingByChatId,
    takeoverByChatId,
    filters,
    closingLead,
    updatingLeadStatus,
    listTab,
    needsResponseChatIds,
    displayListItems,
    activeTakeover,
    isInputBlocked,
    isSenior,
    fetchList,
    refreshCurrentChatOwner,
    openChat,
    closeChat,
    loadOlderMessages,
    sendMessage,
    handleInboundMessage,
    handleAttachmentReady,
    handleTakeoverStarted,
    handleTakeoverReleased,
    setTyping,
    bumpChatInList,
    clearHighlight,
    handleOwnershipChanged,
    handleEscalationOwnerNotify,
    handleEscalationGroupNotify,
    handleMessageOnBehalf,
    setContactOwnership,
    handleLeadEvent,
    closeCurrentLead,
    updateCurrentLeadStatus,
    updateCurrentLeadComment,
    updateChatLabel,
    patchChatLead,
  }
})

export type ChatsStore = ReturnType<typeof useChatsStore>
