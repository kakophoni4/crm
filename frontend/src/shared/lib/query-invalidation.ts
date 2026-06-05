type Listener = () => void

const contactsListeners = new Set<Listener>()
const chatsListeners = new Set<Listener>()

export function onContactsInvalidate(listener: Listener): () => void {
  contactsListeners.add(listener)
  return () => contactsListeners.delete(listener)
}

/** Stub for vue-query `invalidateQueries` — bumps subscribers on WS `contacts.*` events. */
export function invalidateContactsQueries(): void {
  contactsListeners.forEach((listener) => listener())
}

export function onChatsInvalidate(listener: Listener): () => void {
  chatsListeners.add(listener)
  return () => chatsListeners.delete(listener)
}

export function invalidateChatsQueries(): void {
  chatsListeners.forEach((listener) => listener())
}
