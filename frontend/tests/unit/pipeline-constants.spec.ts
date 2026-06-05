import { describe, expect, it } from 'vitest'

import {
  isPipelineStageDeletable,
  isPipelineStageVisibleInAdmin,
  PIPELINE_DEFAULT_OPEN_CODES,
  PIPELINE_HIDDEN_ADMIN_CODES,
  PIPELINE_PROTECTED_DELETE_CODES,
} from '@/features/leads/pipeline-constants'

describe('pipeline constants', () => {
  it('defines default open and hidden terminal codes', () => {
    expect(PIPELINE_DEFAULT_OPEN_CODES).toEqual(['new', 'in_progress'])
    expect(PIPELINE_HIDDEN_ADMIN_CODES).toEqual(['won', 'lost'])
    expect(PIPELINE_PROTECTED_DELETE_CODES).toEqual(['new', 'in_progress', 'won', 'lost'])
  })

  it('hides won/lost from admin funnel', () => {
    expect(isPipelineStageVisibleInAdmin('won')).toBe(false)
    expect(isPipelineStageVisibleInAdmin('in_progress')).toBe(true)
  })

  it('protects system stages from deletion', () => {
    expect(isPipelineStageDeletable('new')).toBe(false)
    expect(isPipelineStageDeletable('custom_stage')).toBe(true)
  })
})
