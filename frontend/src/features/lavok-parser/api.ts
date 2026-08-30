import { http } from '@/shared/api/http'

import type {
  LavokParserIngestResponse,
  LavokParserListResponse,
  LavokParserLot,
} from '@/features/lavok-parser/types'

export async function listLavokLots(params: {
  sheet_date?: string | null
  q?: string
  mark?: string | null
  favorite?: boolean
  limit?: number
  offset?: number
}): Promise<LavokParserListResponse> {
  const { data } = await http.get<LavokParserListResponse>('/lavok-parser', {
    params: {
      sheet_date: params.sheet_date ?? undefined,
      q: params.q,
      mark: params.mark || undefined,
      favorite: params.favorite || undefined,
      limit: params.limit,
      offset: params.offset,
    },
  })
  return data
}

export async function ingestLavokXlsx(file: File): Promise<LavokParserIngestResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<LavokParserIngestResponse>('/lavok-parser/ingest', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
  return data
}

export async function patchLavokLot(
  lotId: number,
  body: { mark?: string; note?: string | null; is_favorite?: boolean },
): Promise<LavokParserLot> {
  const { data } = await http.patch<LavokParserLot>(`/lavok-parser/${lotId}`, body)
  return data
}

export async function deleteLavokLot(lotId: number): Promise<void> {
  await http.delete(`/lavok-parser/${lotId}`)
}
