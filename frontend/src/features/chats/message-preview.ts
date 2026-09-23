/** Human-readable chat list preview (hides legacy bot placeholder). */
export function formatChatMessagePreview(preview: string | null | undefined): string {
  if (!preview?.trim()) return '—'
  if (isAttachmentPlaceholderText(preview)) return 'Вложение'
  if (/^(?:file_|voice[_-])[^\s/]*\.(?:oga|ogg|opus)$/i.test(preview.trim())) return 'Голосовое сообщение'
  return preview
}

export function isAttachmentPlaceholderText(text: string | null | undefined): boolean {
  if (!text?.trim()) return false
  const normalized = text.trim().toLowerCase()
  return normalized === '[attachment]' || normalized === 'attachment'
}
