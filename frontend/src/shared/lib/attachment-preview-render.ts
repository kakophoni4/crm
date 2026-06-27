import type { AttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'

export async function renderAttachmentPreviewHtml(
  kind: AttachmentPreviewKind,
  blob: Blob,
): Promise<string | null> {
  if (kind === 'text') {
    const text = await blob.text()
    return `<pre class="attachment-preview-text">${escapeHtml(text)}</pre>`
  }
  if (kind === 'docx') {
    const mammoth = await import('mammoth')
    const result = await mammoth.convertToHtml({ arrayBuffer: await blob.arrayBuffer() })
    return `<div class="attachment-preview-doc">${result.value}</div>`
  }
  if (kind === 'spreadsheet') {
    const XLSX = await import('xlsx')
    const workbook = XLSX.read(await blob.arrayBuffer(), { type: 'array' })
    const sheetName = workbook.SheetNames[0]
    if (!sheetName) return '<p>Пустая таблица</p>'
    return XLSX.utils.sheet_to_html(workbook.Sheets[sheetName], { id: 'attachment-sheet-table' })
  }
  return null
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
