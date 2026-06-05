let focusHandler: (() => void) | null = null

export function registerChatListSearchFocus(handler: (() => void) | null): void {
  focusHandler = handler
}

export function focusChatListSearch(): void {
  focusHandler?.()
}
