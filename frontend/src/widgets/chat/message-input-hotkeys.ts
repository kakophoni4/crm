/** Enter — send; Shift+Enter — new line in textarea. */
export function isMessageSendShortcut(event: KeyboardEvent): boolean {
  if (event.key !== 'Enter') return false
  if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return false
  return true
}

/** Shift+Enter — insert newline without sending. */
export function isMessageNewlineShortcut(event: KeyboardEvent): boolean {
  if (event.key !== 'Enter') return false
  return event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey
}
