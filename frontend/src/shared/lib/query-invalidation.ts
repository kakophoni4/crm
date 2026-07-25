import type { ContactListPatch } from '@/shared/realtime/contact-list-patch'

/** Coalesce burst callbacks (WS storms) into a single flush. Reusable for other domains. */
export function createDebouncedFlush(delayMs: number): {
  schedule: (fn: () => void) => void
  cancel: () => void
  flush: () => void
} {
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: (() => void) | null = null

  const cancel = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    pending = null
  }

  const flush = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    const fn = pending
    pending = null
    fn?.()
  }

  const schedule = (fn: () => void): void => {
    pending = fn
    if (timer != null) clearTimeout(timer)
    timer = setTimeout(flush, delayMs)
  }

  return { schedule, cancel, flush }
}

export type { ContactListPatch }

export interface ContactsInvalidateEvent {
  patch?: ContactListPatch
  reload?: boolean
}

type ContactsListener = (event: ContactsInvalidateEvent) => void
type ChatsListener = () => void

const CONTACTS_RELOAD_DEBOUNCE_MS = 400
const CHATS_INVALIDATE_DEBOUNCE_MS = 400

const contactsListeners = new Set<ContactsListener>()
const contactsReloadDebouncer = createDebouncedFlush(CONTACTS_RELOAD_DEBOUNCE_MS)
const chatsListeners = new Set<ChatsListener>()
const chatsReloadDebouncer = createDebouncedFlush(CHATS_INVALIDATE_DEBOUNCE_MS)

function notifyContacts(event: ContactsInvalidateEvent): void {
  contactsListeners.forEach((listener) => listener(event))
}

export function onContactsInvalidate(listener: ContactsListener): () => void {
  contactsListeners.add(listener)
  return () => contactsListeners.delete(listener)
}

export interface InvalidateContactsOptions {
  patch?: ContactListPatch
  /** Skip debounce — use after explicit user mutations (create contact). */
  immediate?: boolean
  /** Force debounced full reload even when a row patch is provided. */
  reload?: boolean
}

/** Stub for vue-query `invalidateQueries` — subscribers on WS `contact.*` / ownership events. */
export function invalidateContactsQueries(opts?: InvalidateContactsOptions): void {
  if (opts?.patch) {
    notifyContacts({ patch: opts.patch })
  }

  const fireReload = (): void => notifyContacts({ reload: true })
  const wantReload = opts?.immediate === true || opts?.reload === true || !opts?.patch

  if (!wantReload) {
    // Patch-only: avoid REST storm when the row can be updated locally.
    return
  }

  if (opts?.immediate) {
    contactsReloadDebouncer.cancel()
    fireReload()
  } else {
    contactsReloadDebouncer.schedule(fireReload)
  }
}

export function onChatsInvalidate(listener: ChatsListener): () => void {
  chatsListeners.add(listener)
  return () => chatsListeners.delete(listener)
}

export interface InvalidateChatsOptions {
  /** Skip debounce — use after explicit user mutations (create contact). */
  immediate?: boolean
}

export function invalidateChatsQueries(opts?: InvalidateChatsOptions): void {
  const fire = (): void => {
    chatsListeners.forEach((listener) => listener())
  }

  if (opts?.immediate) {
    chatsReloadDebouncer.cancel()
    fire()
  } else {
    chatsReloadDebouncer.schedule(fire)
  }
}
