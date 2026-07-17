const DEFAULT_MAX_UPLOAD_PHOTO_BYTES = 10 * 1024 * 1024
const DEFAULT_MAX_UPLOAD_FILE_BYTES = 100 * 1024 * 1024

function parseBytes(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export const MAX_UPLOAD_PHOTO_BYTES = parseBytes(
  import.meta.env.VITE_MAX_UPLOAD_PHOTO_BYTES,
  DEFAULT_MAX_UPLOAD_PHOTO_BYTES,
)

export const MAX_UPLOAD_FILE_BYTES = parseBytes(
  import.meta.env.VITE_MAX_UPLOAD_FILE_BYTES,
  DEFAULT_MAX_UPLOAD_FILE_BYTES,
)

export function isPhotoFile(file: File): boolean {
  return file.type.startsWith('image/')
}

export function maxUploadBytesFor(file: File): number {
  return isPhotoFile(file) ? MAX_UPLOAD_PHOTO_BYTES : MAX_UPLOAD_FILE_BYTES
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function uploadLimitLabel(file: File): string {
  return isPhotoFile(file)
    ? `фото — ${formatFileSize(MAX_UPLOAD_PHOTO_BYTES)}`
    : `файлы — ${formatFileSize(MAX_UPLOAD_FILE_BYTES)}`
}
