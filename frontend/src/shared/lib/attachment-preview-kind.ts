export type AttachmentPreviewKind =
  | 'image'
  | 'pdf'
  | 'text'
  | 'docx'
  | 'spreadsheet'
  | 'unsupported'

function fileName(att: Record<string, unknown>): string {
  const raw = att.filename ?? att.name
  return typeof raw === 'string' ? raw.toLowerCase() : ''
}

function mimeType(att: Record<string, unknown>): string {
  const raw = att.mime
  return typeof raw === 'string' ? raw.toLowerCase() : ''
}

export function resolveAttachmentPreviewKind(att: Record<string, unknown>): AttachmentPreviewKind {
  const mime = mimeType(att)
  const name = fileName(att)

  if (
    att.type === 'photo' ||
    mime.startsWith('image/') ||
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg') ||
    name.endsWith('.png') ||
    name.endsWith('.gif') ||
    name.endsWith('.webp') ||
    name.endsWith('.bmp') ||
    name.endsWith('.svg') ||
    name.endsWith('.heic') ||
    name.endsWith('.heif') ||
    name.endsWith('.tif') ||
    name.endsWith('.tiff') ||
    name.endsWith('.avif')
  ) {
    return 'image'
  }
  if (mime === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (
    mime.startsWith('text/') ||
    name.endsWith('.txt') ||
    name.endsWith('.log') ||
    name.endsWith('.md')
  ) {
    return 'text'
  }
  if (
    mime.includes('wordprocessingml') ||
    mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    name.endsWith('.docx')
  ) {
    return 'docx'
  }
  if (
    mime.includes('spreadsheetml') ||
    mime.includes('ms-excel') ||
    mime === 'application/csv' ||
    mime === 'text/csv' ||
    name.endsWith('.xlsx') ||
    name.endsWith('.xls') ||
    name.endsWith('.csv')
  ) {
    return 'spreadsheet'
  }
  return 'unsupported'
}

export function attachmentPreviewSupported(kind: AttachmentPreviewKind): boolean {
  return kind !== 'unsupported'
}
