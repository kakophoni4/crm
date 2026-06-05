/** Must match app/modules/leads/pipeline_constants.py */

/** Default open pipeline stages (senior adds more manually). */
export const PIPELINE_DEFAULT_OPEN_CODES = ['new', 'in_progress'] as const

/** Set only via «Успешная / Неуспешная продажа», hidden from funnel admin. */
export const PIPELINE_HIDDEN_ADMIN_CODES = ['won', 'lost'] as const

export const PIPELINE_PROTECTED_DELETE_CODES = [
  ...PIPELINE_DEFAULT_OPEN_CODES,
  ...PIPELINE_HIDDEN_ADMIN_CODES,
] as const

export function isPipelineStageDeletable(code: string): boolean {
  return !(PIPELINE_PROTECTED_DELETE_CODES as readonly string[]).includes(code)
}

export function isPipelineStageVisibleInAdmin(code: string): boolean {
  return !(PIPELINE_HIDDEN_ADMIN_CODES as readonly string[]).includes(code)
}
