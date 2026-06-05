import { vi } from 'vitest'

vi.mock('@/features/groups/directory', () => ({
  ensureGroupDirectory: vi.fn().mockResolvedValue(undefined),
  lookupGroupName: vi.fn(() => null),
  resetGroupDirectoryCacheForTests: vi.fn(),
}))
