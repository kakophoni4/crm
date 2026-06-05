const DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

function parseMaxUploadBytes(): number {
  const raw = import.meta.env.VITE_MAX_UPLOAD_BYTES
  if (!raw) return DEFAULT_MAX_UPLOAD_BYTES
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_UPLOAD_BYTES
}

export const MAX_UPLOAD_BYTES = parseMaxUploadBytes()

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
