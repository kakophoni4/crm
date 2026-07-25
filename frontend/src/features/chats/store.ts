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
  TakeoverState,
} from '@/entities/chat/types'
import {
  closeLead as closeLeadApi,
  createContactLead,
  patchLead as patchLeadApi,
} from '@/features/leads/api'
import type { GroupOwnershipItem } from '@/entities/contact/types'
import * as chatsApi from '@/features/chats/api'
import {
  applyOwnershipToChat,
  enrichMessagesWithReplyAudit,
  ownershipKey,
} from '@/features/chats/ownership-enrich'
import { chatWorkflowLabelPatch, chatListItemIsAnswered, chatListItemNeedsResponse } from '@/features/leads/mapping'
import {
  hydrateChatsDiskCaches,
  peekPersistedChatList,
  persistChatList,
} from '@/features/chats/chats-disk-cache'
import { scheduleDealsPrefetchFromList } from '@/features/chats/deals-cache'
import {
  CHAT_SNAPSHOT_CACHE_SIZE,
  getChatSnapshot,
  isChatSnapshotFresh,
  priorityPrefetchChat,
  scheduleChatSnapshotsPrefetch,
  setChatSnapshot,
  waitForChatSnapshot,
} from '@/features/chats/snapshot-cache'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { priorityPrefetchAttachmentsForMessages } from '@/shared/lib/attachment-blob-cache'
import { formatChatMessagePreview } from '@/features/chats/message-preview'
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
  const selectedLeadId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const messagesLoading = ref(false)
  const loadingOlderMessages = ref(false)
  const messagesNextCursor = ref<string | null>(null)

  const typingByChatId = ref<Record<number, boolean>>({})
  const takeoverByChatId = ref<Record<number, TakeoverState>>({})

  const listTab = ref<ChatListTab>('mine')
  const needsResponseChatIds = ref<Set<number>>(new Set())
  const ownershipByKey = ref<Record<string, GroupOwnershipItem>>({})

  const filters = ref({
    q: '',
    botId: null as number | null,
    unreadOnly: false,
    leadStatusId: null as number | null,
    leadOpenOnly: false,
    sort: 'last_message_at_desc' as ChatListSort,
  })

  const closingLead = ref(false)
  const updatingLeadStatus = ref(false)
  const creatingLead = ref(false)
  const updatingLeadFields = ref(false)
  const optOrdersRefreshNonce = ref(0)

  function bumpOptOrdersRefresh(): void {
    optOrdersRefreshNonce.value += 1
  }

  /** Bumps on each openChat(); stale async results are ignored. */
  let openChatSeq = 0
  /** Bumps on each non-append fetchList(); stale list responses are ignored. */
  let listFetchSeq = 0
  /** Coalesce overlapping WS-driven message refreshes per chat. */
  const refreshInflight = new Map<number, Promise<void>>()
  const refreshQueuedMessageId = new Map<number, number>()
  /** Debounce silent list reloads so WS bursts don't stampede GET /chats. */
  let silentListTimer: ReturnType<typeof setTimeout> | null = null

  function isActiveChat(chatId: number, seq: number): boolean {
    return seq === openChatSeq && currentChatId.value === chatId
  }

  function finishMessagesLoad(seq: number): void {
    if (seq === openChatSeq) {
      messagesLoading.value = false
    }
  }

  function toChronological(items: ChatMessage[]): ChatMessage[] {
    if (items.length <= 1) return items
    let ordered = true
    for (let i = 1; i < items.length; i += 1) {
      const prev = items[i - 1]
      const next = items[i]
      if (
        prev.created_at > next.created_at ||
        (prev.created_at === next.created_at && prev.id > next.id)
      ) {
        ordered = false
        break
      }
    }
    if (ordered) return items
    return [...items].sort((a, b) => {
      if (a.created_at !== b.created_at) {
        return a.created_at < b.created_at ? -1 : 1
      }
      return a.id - b.id
    })
  }

  function persistOpenChatSnapshot(chatId: number): void {
    if (!currentChat.value || currentChat.value.id !== chatId) return
    setChatSnapshot(
      chatId,
      {
        detail: currentChat.value,
        messages: messages.value,
        nextCursor: messagesNextCursor.value,
      },
      { prefetchAttachments: false },
    )
  }

  function upsertMessageInList(list: ChatMessage[], saved: ChatMessage, clientKey: string): ChatMessage[] {
    const idx = list.findIndex((m) => m._clientKey === clientKey || m.id === saved.id)
    if (idx >= 0) {
      const next = list.slice()
      next[idx] = { ...saved, _clientKey: clientKey }
      return next
    }
    return toChronological([...list, { ...saved, _clientKey: clientKey }])
  }

  /** Coalesce background list reloads from WS / invalidation. */
  function scheduleSilentListRefresh(delayMs = 450): void {
    if (silentListTimer != null) clearTimeout(silentListTimer)
    silentListTimer = setTimeout(() => {
      silentListTimer = null
      void fetchList(false, { silent: true })
    }, delayMs)
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
    () =>
      auth.user?.role === 'senior' ||
      auth.user?.role === 'group_senior' ||
      auth.user?.role === 'admin',
  )

  const listInitialLoading = computed(() => listLoading.value && !listLoaded.value)

  const displayListItems = computed(() => listItems.value)

  function buildListQuery(append: boolean): ChatListParams {
    const me = auth.user?.id
    const params: ChatListParams = {
      q: filters.value.q.trim() || undefined,
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

  async function closeCurrentLead(statusId: number, leadId?: number): Promise<void> {
    const lead =
      leadId != null
        ? { id: leadId, closed_at: null }
        : currentChat.value?.current_lead
    if (!lead || lead.closed_at != null || closingLead.value) return
    closingLead.value = true
    try {
      await closeLeadApi(lead.id, statusId)
      if (currentChatId.value != null && currentChat.value?.current_lead?.id === lead.id) {
        patchChatLead(currentChatId.value, null)
        await refreshChatLead(currentChatId.value)
        await reloadMessages()
      } else if (selectedLeadId.value === lead.id) {
        selectedLeadId.value = null
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

  async function updateCurrentLeadCustomFields(
    customFields: Record<string, unknown>,
  ): Promise<void> {
    const lead = currentChat.value?.current_lead
    if (!lead || lead.closed_at != null || updatingLeadFields.value) return
    updatingLeadFields.value = true
    try {
      await patchLeadApi(lead.id, { custom_fields: customFields })
    } finally {
      updatingLeadFields.value = false
    }
  }

  async function createManualLead(): Promise<CurrentLeadSnippet | null> {
    const chat = currentChat.value
    if (!chat || creatingLead.value) return null
    const groupId = chat.assigned_group_id
    if (groupId == null) {
      throw new Error('Назначьте боту группу, чтобы открыть сделку')
    }
    creatingLead.value = true
    try {
      const created = await createContactLead(chat.contact_id, {
        group_id: groupId,
        bot_id: chat.bot_id,
      })
      const snippet: CurrentLeadSnippet = {
        id: created.id,
        status_id: created.status_id ?? 0,
        label: created.status_label ?? '',
        comment: created.comment ?? null,
        closed_at: created.closed_at,
      }
      if (currentChatId.value != null) {
        patchChatLead(currentChatId.value, snippet)
        selectedLeadId.value = snippet.id
        await refreshChatLead(currentChatId.value)
      }
      await reloadMessages()
      return snippet
    } finally {
      creatingLead.value = false
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

  function clearNeedsResponseForChat(chatId: number): void {
    clearHighlight(chatId)

    const nextNeedsResponse = new Set(needsResponseChatIds.value)
    nextNeedsResponse.delete(chatId)
    needsResponseChatIds.value = nextNeedsResponse

    const patch = {
      needs_response: false,
      needs_reply: false,
      pending_inbound_at: null,
      escalated_at: null,
    } satisfies Partial<ChatListItem>

    const shouldHideFromCurrentTab = listTab.value === 'needs_response'
    listItems.value = listItems.value
      .map((chat) => (chat.id === chatId ? { ...chat, ...patch } : chat))
      .filter((chat) => !(shouldHideFromCurrentTab && chat.id === chatId))

    if (currentChatId.value === chatId && currentChat.value) {
      currentChat.value = { ...currentChat.value, ...patch }
      const groupId = currentChat.value.assigned_group_id
      if (groupId != null) {
        const key = ownershipKey(currentChat.value.contact_id, groupId)
        const ownership = ownershipByKey.value[key]
        if (ownership) {
          ownershipByKey.value = {
            ...ownershipByKey.value,
            [key]: {
              ...ownership,
              pending_inbound_at: null,
              escalated_at: null,
            },
          }
        }
      }
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

  function hydrateFromDisk(): void {
    hydrateChatsDiskCaches()
    if (listItems.value.length > 0) return
    const cached = peekPersistedChatList()
    if (!cached?.items.length) return
    listItems.value = enrichWithGroupNames(cached.items).map((chat) => ({
      ...chat,
      needs_response: chatListItemNeedsResponse(chat),
    }))
    listNextCursor.value = cached.nextCursor
    listLoaded.value = true
    needsResponseChatIds.value = new Set(
      listItems.value.filter((chat) => chatListItemNeedsResponse(chat)).map((chat) => chat.id),
    )
    // Warm deals/snapshots from list while network list refreshes.
    scheduleDealsPrefetchFromList(listItems.value.slice(0, 8))
    scheduleChatSnapshotsPrefetch(
      listItems.value.slice(0, 2).map((c) => c.id),
      { priority: true },
    )
  }

  async function fetchList(
    append = false,
    opts?: { silent?: boolean },
  ): Promise<void> {
    // Background refresh (WS / inbound / load-more) must NOT overlay NSpin — it blocks clicks.
    const silent =
      opts?.silent === true || (listLoaded.value && listItems.value.length > 0)
    const seq = append ? listFetchSeq : ++listFetchSeq
    if (!silent) listLoading.value = true
    if (!append) listError.value = null
    try {
      try {
        await ensureGroupDirectory()
      } catch {
        // Fail-soft: list still works without group name enrichment.
      }
      const data = await chatsApi.listChats(buildListQuery(append))
      // A newer non-append fetch won — drop this response (including stale append).
      if (seq !== listFetchSeq) return
      const items = enrichWithGroupNames(data?.items ?? [])
      listItems.value = enrichListWithOwnership(append ? [...listItems.value, ...items] : items).map(
        (chat) => ({
          ...chat,
          needs_response: chatListItemNeedsResponse(chat),
        }),
      )
      if (!append) {
        needsResponseChatIds.value = new Set(
          listItems.value.filter((chat) => chatListItemNeedsResponse(chat)).map((chat) => chat.id),
        )
        highlightedChatIds.value = new Set(
          [...highlightedChatIds.value].filter((id) => {
            const chat = listItems.value.find((row) => row.id === id)
            return chat != null && !chatListItemIsAnswered(chat)
          }),
        )
        persistChatList(listItems.value, data?.next_cursor ?? null)
      }
      listNextCursor.value = data?.next_cursor ?? null
    } catch (err) {
      if (seq !== listFetchSeq) return
      if (!append) {
        // Keep disk-hydrated list on network failure instead of wiping UI.
        if (listItems.value.length === 0) {
          listItems.value = []
        }
        listError.value = err instanceof Error ? err.message : 'Не удалось загрузить чаты'
      }
      throw err
    } finally {
      if (seq === listFetchSeq) {
        listLoading.value = false
        listLoaded.value = true
      }
      if (!append && seq === listFetchSeq && listItems.value.length > 0) {
        // Keep background warm-up small — full-list prefetch saturates the browser.
        const topIds = listItems.value.slice(0, 8).map((chat) => chat.id)
        scheduleChatSnapshotsPrefetch(topIds.slice(0, 2), { priority: true })
        if (topIds.length > 2) {
          scheduleChatSnapshotsPrefetch(topIds.slice(2))
        }
        // Deals/заявки — сразу с list item, не ждать полного snapshot сообщений.
        scheduleDealsPrefetchFromList(listItems.value.slice(0, 6))
      }
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
        filters.value.botId,
        filters.value.unreadOnly,
        filters.value.leadStatusId,
        filters.value.leadOpenOnly,
      ] as const,
    () => {
      void fetchList()
    },
  )

  async function selectLead(leadId: number | null): Promise<void> {
    selectedLeadId.value = leadId
  }

  async function reloadMessages(): Promise<void> {
    if (!currentChatId.value || !currentChat.value) return
    const chatId = currentChatId.value
    const seq = openChatSeq
    messagesLoading.value = true
    try {
      const msgs = await chatsApi.listMessages(chatId, {
        limit: 50,
      })
      if (!isActiveChat(chatId, seq)) return

      const chronological = toChronological(msgs.items)
      messages.value = chronological
      messagesNextCursor.value = msgs.next_cursor
      finishMessagesLoad(seq)

      setChatSnapshot(
        chatId,
        {
          detail: currentChat.value,
          messages: chronological,
          nextCursor: msgs.next_cursor,
        },
        { prefetchAttachments: false },
      )

      void enrichMessagesWithReplyAudit(
        currentChat.value.contact_id,
        currentChat.value.assigned_group_id,
        chronological,
      ).then((enriched) => {
        if (!isActiveChat(chatId, seq)) return
        messages.value = toChronological(enriched)
      })
    } finally {
      finishMessagesLoad(seq)
    }
  }

  async function syncChatFromNetwork(chatId: number, seq: number): Promise<void> {
    const [detail, msgs] = await Promise.all([
      chatsApi.getChat(chatId),
      chatsApi.listMessages(chatId, {
        limit: 50,
      }),
    ])
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

    const merged = mergeNetworkMessages(toChronological(msgs.items))
    messages.value = merged
    messagesNextCursor.value = msgs.next_cursor
    finishMessagesLoad(seq)

    setChatSnapshot(
      chatId,
      {
        detail: currentChat.value,
        messages: merged,
        nextCursor: msgs.next_cursor,
      },
      { prefetchAttachments: false },
    )

    void enrichMessagesWithReplyAudit(
      detail.contact_id,
      detail.assigned_group_id,
      merged,
    ).then((enriched) => {
      if (!isActiveChat(chatId, seq)) return
      messages.value = mergeNetworkMessages(enriched)
    })

    void chatsApi.markChatRead(chatId).catch(() => undefined)
    const idx = listItems.value.findIndex((c) => c.id === chatId)
    if (idx >= 0) {
      listItems.value[idx] = {
        ...listItems.value[idx],
        unread_for_me: false,
      }
    }
  }

  async function openChat(chatId: number): Promise<void> {
    const prevChatId = currentChatId.value
    if (prevChatId != null && prevChatId !== chatId) {
      persistOpenChatSnapshot(prevChatId)
    }

    const seq = ++openChatSeq
    loadingOlderMessages.value = false
    currentChatId.value = chatId
    selectedLeadId.value = null
    clearHighlight(chatId)

    let snapshot = getChatSnapshot(chatId)
    const cached = listItems.value.find((c) => c.id === chatId)
    currentChat.value = snapshot?.detail ?? (cached ? ({ ...cached } as ChatDetail) : null)

    // Telegram-style: switch the thread pane immediately.
    // Never keep previous chat bubbles while waiting for prefetch/network.
    if (snapshot) {
      messages.value = toChronological(snapshot.messages)
      messagesNextCursor.value = snapshot.nextCursor
      messagesLoading.value = false
      priorityPrefetchAttachmentsForMessages(snapshot.messages)
    } else {
      messages.value = []
      messagesNextCursor.value = null
      messagesLoading.value = true
      priorityPrefetchChat(chatId)
    }

    try {
      void ensureGroupDirectory()
      if (snapshot) {
        // Fresh cache: don't immediately fight the UI with getChat+listMessages.
        if (isChatSnapshotFresh(chatId, 20_000)) {
          window.setTimeout(() => {
            if (isActiveChat(chatId, seq)) void syncChatFromNetwork(chatId, seq)
          }, 1500)
        } else {
          void syncChatFromNetwork(chatId, seq)
        }
        return
      }

      // Empty spinner is OK; wrong-chat content is not. Short wait for in-flight prefetch.
      const waited = await waitForChatSnapshot(chatId, 600)
      if (!isActiveChat(chatId, seq)) return
      if (waited) {
        snapshot = waited
        currentChat.value = waited.detail
        messages.value = waited.messages
        messagesNextCursor.value = waited.nextCursor
        messagesLoading.value = false
        priorityPrefetchAttachmentsForMessages(waited.messages)
        void syncChatFromNetwork(chatId, seq)
        return
      }
      await syncChatFromNetwork(chatId, seq)
    } finally {
      finishMessagesLoad(seq)
    }
  }

  function closeChat(): void {
    openChatSeq += 1
    messagesLoading.value = false
    loadingOlderMessages.value = false
    currentChatId.value = null
    currentChat.value = null
    selectedLeadId.value = null
    messages.value = []
    messagesNextCursor.value = null
  }

  async function loadOlderMessages(): Promise<void> {
    if (
      !currentChatId.value ||
      !messagesNextCursor.value ||
      !currentChat.value ||
      loadingOlderMessages.value
    ) {
      return
    }
    const chatId = currentChatId.value
    const seq = openChatSeq
    loadingOlderMessages.value = true
    try {
      const data = await chatsApi.listMessages(chatId, {
        cursor: messagesNextCursor.value,
        limit: 50,
      })
      if (!isActiveChat(chatId, seq) || !currentChat.value) return
      const older = await enrichMessagesWithReplyAudit(
        currentChat.value.contact_id,
        currentChat.value.assigned_group_id,
        toChronological(data.items),
      )
      if (!isActiveChat(chatId, seq)) return
      messages.value = [...older, ...messages.value]
      messagesNextCursor.value = data.next_cursor
    } catch {
      /* keep cursor; user can retry scroll */
    } finally {
      loadingOlderMessages.value = false
    }
  }

  async function sendMessage(
    text: string,
    attachments: { file_id: number; name?: string; mime?: string }[] = [],
    replyToMessageId: number | null = null,
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
      sender_username: auth.user?.username?.trim() || auth.user?.full_name?.trim() || null,
      reply_to_message_id: replyToMessageId,
      created_at: new Date().toISOString(),
      idempotency_key: clientKey,
      _optimistic: true,
      _clientKey: clientKey,
    }
    messages.value.push(optimistic)
    persistOpenChatSnapshot(chatId)
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
        reply_to_message_id: replyToMessageId,
      })
      // Critical: never apply the POST result to a different open chat.
      if (currentChatId.value === chatId) {
        messages.value = upsertMessageInList(messages.value, saved, clientKey)
        persistOpenChatSnapshot(chatId)
      } else {
        const snap = getChatSnapshot(chatId)
        if (snap) {
          setChatSnapshot(
            chatId,
            {
              detail: snap.detail,
              messages: upsertMessageInList(snap.messages, saved, clientKey),
              nextCursor: snap.nextCursor,
            },
            { prefetchAttachments: false },
          )
        }
      }
      void chatsApi.markChatRead(chatId, { last_read_message_id: saved.id }).catch(() => undefined)
      clearNeedsResponseForChat(chatId)
      const answeredPatch = chatWorkflowLabelPatch('answered')
      const listIdx = listItems.value.findIndex((c) => c.id === chatId)
      if (listIdx >= 0) {
        listItems.value[listIdx] = {
          ...listItems.value[listIdx],
          unread_for_me: false,
          ...answeredPatch,
        }
      }
      if (currentChatId.value === chatId && currentChat.value) {
        currentChat.value = { ...currentChat.value, ...answeredPatch }
      }
    } catch (err) {
      if (currentChatId.value === chatId) {
        const idx = messages.value.findIndex((m) => m._clientKey === clientKey)
        if (idx >= 0) {
          messages.value[idx] = {
            ...messages.value[idx],
            _failed: true,
          }
        }
      } else {
        const snap = getChatSnapshot(chatId)
        if (snap) {
          const idx = snap.messages.findIndex((m) => m._clientKey === clientKey)
          if (idx >= 0) {
            const next = snap.messages.slice()
            next[idx] = { ...next[idx], _failed: true }
            setChatSnapshot(
              chatId,
              { detail: snap.detail, messages: next, nextCursor: snap.nextCursor },
              { prefetchAttachments: false },
            )
          }
        }
      }
      throw err
    }
  }

  function patchChatResponseState(
    chatId: number,
    patch: Partial<ChatListItem>,
  ): void {
    bumpChatInList(chatId, patch, true)

    if (currentChatId.value === chatId && currentChat.value) {
      currentChat.value = { ...currentChat.value, ...patch }
    }

    const chat = listItems.value.find((row) => row.id === chatId)
    if (chat?.assigned_group_id == null) return

    const key = ownershipKey(chat.contact_id, chat.assigned_group_id)
    const prev = ownershipByKey.value[key]
    ownershipByKey.value = {
      ...ownershipByKey.value,
      [key]: {
        group_id: chat.assigned_group_id,
        group_name: prev?.group_name ?? lookupGroupName(chat.assigned_group_id) ?? '',
        owner_user_id: prev?.owner_user_id ?? chat.card_owner_user_id ?? null,
        owner_full_name: prev?.owner_full_name ?? chat.card_owner_full_name ?? null,
        pending_inbound_at:
          patch.pending_inbound_at !== undefined
            ? patch.pending_inbound_at
            : (prev?.pending_inbound_at ?? chat.pending_inbound_at ?? null),
        escalated_at:
          patch.escalated_at !== undefined
            ? patch.escalated_at
            : (prev?.escalated_at ?? chat.escalated_at ?? null),
      },
    }
  }

  function appendOptimisticBubble(
    chatId: number,
    messageId: number,
    direction: 'inbound' | 'outbound',
    preview: string | undefined,
    createdAt: string,
  ): void {
    if (!Number.isFinite(messageId) || messageId <= 0) return
    if (messages.value.some((m) => m.id === messageId)) return
    messages.value = [
      ...messages.value,
      {
        id: messageId,
        chat_id: chatId,
        direction,
        kind: 'text',
        text: preview ?? null,
        attachments: [],
        sender_user_id: null,
        sender_username: null,
        reply_to_message_id: null,
        created_at: createdAt,
      },
    ]
    if (currentChat.value?.id === chatId) {
      setChatSnapshot(
        chatId,
        {
          detail: currentChat.value,
          messages: messages.value,
          nextCursor: messagesNextCursor.value,
        },
        { prefetchAttachments: false },
      )
    }
  }

  /** Keep WS stubs that API page has not caught up with yet. */
  function mergeNetworkMessages(incoming: ChatMessage[]): ChatMessage[] {
    if (!incoming.length) return messages.value
    const byId = new Map(incoming.map((m) => [m.id, m]))
    const maxNetId = incoming.reduce((max, m) => (m.id > max ? m.id : max), 0)
    for (const local of messages.value) {
      if (local.id > 0 && local.id > maxNetId && !byId.has(local.id)) {
        byId.set(local.id, local)
      }
    }
    return [...byId.values()].sort((a, b) => {
      if (a.created_at !== b.created_at) {
        return a.created_at < b.created_at ? -1 : 1
      }
      return a.id - b.id
    })
  }

  async function handleInboundMessage(payload: Record<string, unknown>): Promise<void> {
    const chatId = Number(payload.chat_id)
    if (!Number.isFinite(chatId)) return

    const now = new Date().toISOString()
    const preview =
      typeof payload.text_preview === 'string' ? payload.text_preview.slice(0, 200) : undefined

    patchChatResponseState(chatId, {
      unread_for_me: currentChatId.value !== chatId,
      last_message_at: now,
      ...(preview ? { last_message_preview: formatChatMessagePreview(preview) } : {}),
      ...chatWorkflowLabelPatch('waiting'),
      pending_inbound_at: now,
      needs_response: true,
      needs_reply: true,
    })

    const nextNeedsResponse = new Set(needsResponseChatIds.value)
    nextNeedsResponse.add(chatId)
    needsResponseChatIds.value = nextNeedsResponse

    const messageId = Number(payload.message_id)
    if (currentChatId.value === chatId) {
      if (Number.isFinite(messageId) && messageId > 0) {
        // Optimistic stub so the bubble appears even if listMessages is slow/fails.
        appendOptimisticBubble(chatId, messageId, 'inbound', preview, now)
        await refreshOpenChatMessages(chatId, messageId)
      }
    } else {
      // List row already patched above. Full GET /chats + snapshot prefetch on every
      // inbound was the main UI stall under message bursts.
      const known = listItems.value.some((c) => c.id === chatId)
      if (!known) {
        scheduleSilentListRefresh()
      }
    }
  }

  async function handleOutboundMessage(payload: Record<string, unknown>): Promise<void> {
    const chatId = Number(payload.chat_id)
    const messageId = Number(payload.message_id)
    if (!Number.isFinite(chatId)) return

    const now = new Date().toISOString()
    const preview =
      typeof payload.text_preview === 'string' ? payload.text_preview.slice(0, 200) : undefined

    bumpChatInList(
      chatId,
      {
        unread_for_me: false,
        last_message_at: now,
        ...(preview ? { last_message_preview: formatChatMessagePreview(preview) } : {}),
        ...chatWorkflowLabelPatch('answered'),
      },
      false,
    )
    clearNeedsResponseForChat(chatId)

    if (currentChatId.value === chatId && currentChat.value) {
      currentChat.value = {
        ...currentChat.value,
        ...chatWorkflowLabelPatch('answered'),
        last_message_at: now,
        ...(preview ? { last_message_preview: formatChatMessagePreview(preview) } : {}),
      }
      if (Number.isFinite(messageId) && messageId > 0) {
        // Own send already replaced optimistic via POST — skip expensive listMessages.
        const existing = messages.value.find((m) => m.id === messageId)
        if (existing && !existing._optimistic) {
          return
        }
        appendOptimisticBubble(chatId, messageId, 'outbound', preview, now)
        await refreshOpenChatMessages(chatId, messageId)
      }
    }
  }

  async function handleAttachmentReady(payload: Record<string, unknown>): Promise<void> {
    const chatId = Number(payload.chat_id)
    const messageId = Number(payload.message_id)
    if (!Number.isFinite(chatId) || currentChatId.value !== chatId) return
    await refreshOpenChatMessages(chatId, messageId)
  }

  async function refreshOpenChatMessages(chatId: number, messageId: number): Promise<void> {
    if (!Number.isFinite(chatId)) return
    refreshQueuedMessageId.set(chatId, messageId)

    // Join an in-flight burst; the loop below drains any ids queued while waiting.
    const existing = refreshInflight.get(chatId)
    if (existing) {
      await existing
      if (!refreshQueuedMessageId.has(chatId) || refreshInflight.has(chatId)) return
    }

    const run = (async () => {
      // Drain coalesced refreshes: one network round-trip per burst.
      while (refreshQueuedMessageId.has(chatId)) {
        const targetMessageId = refreshQueuedMessageId.get(chatId) ?? 0
        refreshQueuedMessageId.delete(chatId)
        await refreshOpenChatMessagesOnce(chatId, targetMessageId)
      }
    })().finally(() => {
      refreshInflight.delete(chatId)
    })
    refreshInflight.set(chatId, run)
    await run
  }

  async function refreshOpenChatMessagesOnce(chatId: number, messageId: number): Promise<void> {
    const seq = openChatSeq
    if (!isActiveChat(chatId, seq) || !currentChat.value) return
    try {
      const msgs = await chatsApi.listMessages(chatId, {
        limit: 50,
      })
      if (!isActiveChat(chatId, seq) || !currentChat.value) return

      const page = toChronological(msgs.items)
      // Show API rows immediately; audit enrich is best-effort and must not delay the bubble.
      const existingIds = new Set(messages.value.map((m) => m.id))
      const fresh = page.filter((m) => !existingIds.has(m.id))
      if (fresh.length > 0) {
        messages.value = mergeNetworkMessages([...messages.value, ...fresh])
      } else {
        const updated = page.find((m) => m.id === messageId)
        if (updated) {
          const idx = messages.value.findIndex((m) => m.id === messageId)
          if (idx >= 0) {
            messages.value[idx] = updated
            messages.value = [...messages.value]
          } else if (messageId > 0) {
            messages.value = mergeNetworkMessages([...messages.value, updated])
          }
        }
        // Never invent a row from "last page item" — API is newest-first and that
        // fallback was a major source of wrong-message / wrong-chat UI glitches.
      }

      const contactId = currentChat.value.contact_id
      const groupId = currentChat.value.assigned_group_id
      void enrichMessagesWithReplyAudit(contactId, groupId, messages.value).then((enriched) => {
        if (!isActiveChat(chatId, seq)) return
        messages.value = mergeNetworkMessages(enriched)
        persistOpenChatSnapshot(chatId)
      })

      persistOpenChatSnapshot(chatId)
    } catch {
      /* list refresh is best-effort; optimistic stub may already be visible */
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
    if (currentChatId.value === chatId) {
      void refreshOpenChatMessages(chatId, 0)
    }
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
    selectedLeadId,
    optOrdersRefreshNonce,
    bumpOptOrdersRefresh,
    messages,
    messagesLoading,
    loadingOlderMessages,
    messagesNextCursor,
    selectLead,
    reloadMessages,
    typingByChatId,
    takeoverByChatId,
    filters,
    closingLead,
    creatingLead,
    updatingLeadStatus,
    updatingLeadFields,
    listTab,
    needsResponseChatIds,
    displayListItems,
    activeTakeover,
    isInputBlocked,
    isSenior,
    fetchList,
    scheduleSilentListRefresh,
    hydrateFromDisk,
    refreshCurrentChatOwner,
    openChat,
    closeChat,
    loadOlderMessages,
    sendMessage,
    handleInboundMessage,
    handleOutboundMessage,
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
    updateCurrentLeadCustomFields,
    createManualLead,
    updateChatLabel,
    patchChatLead,
  }
})

export type ChatsStore = ReturnType<typeof useChatsStore>
