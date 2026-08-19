import { http } from '@/shared/api/http'

import type {
  LavokParserIngestResponse,
  LavokParserListResponse,
  LavokParserLot,
} from '@/features/lavok-parser/types'

export async function listLavokLots(params: {
  sheet_date?: string | null
  q?: string
  limit?: number
  offset?: number
}): Promise<LavokParserListResponse> {
  const { data } = await http.get<LavokParserListResponse>('/lavok-parser', { params })
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
  body: { mark?: string; note?: string | null },
): Promise<LavokParserLot> {
  const { data } = await http.patch<LavokParserLot>(`/lavok-parser/${lotId}`, body)
  return data
}

export async function deleteLavokLot(lotId: number): Promise<void> {
  await http.delete(`/lavok-parser/${lotId}`)
}
