import { describe, expect, it } from 'vitest'

import { resolveAttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'

describe('attachment preview kind', () => {
  it('detects images by filename when mime is missing', () => {
    expect(resolveAttachmentPreviewKind({ name: 'photo_5462914675432429903_y.jpg', mime: '' })).toBe(
      'image',
    )
    expect(
      resolveAttachmentPreviewKind({ filename: 'scan.png', mime: 'application/octet-stream' }),
    ).toBe('image')
  })

  it('detects pdf by filename', () => {
    expect(
      resolveAttachmentPreviewKind({
        type: 'document',
        filename: 'Альянс_требование_Спересурс_прибыль_доки.pdf',
        mime: 'application/octet-stream',
      }),
    ).toBe('pdf')
  })

  it('detects docx and xlsx', () => {
    expect(
      resolveAttachmentPreviewKind({ filename: 'report.docx', mime: 'application/octet-stream' }),
    ).toBe('docx')
    expect(
      resolveAttachmentPreviewKind({ filename: 'table.xlsx', mime: 'application/octet-stream' }),
    ).toBe('spreadsheet')
  })
})
