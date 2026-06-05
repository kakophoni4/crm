import MockAdapter from 'axios-mock-adapter'
import { describe, expect, it } from 'vitest'

import { AppError, createHttpClient } from '@/shared/api/http'

describe('http client', () => {
  it('adds X-Request-Id on requests', async () => {
    const client = createHttpClient()
    const mock = new MockAdapter(client)
    mock.onGet('/health').reply((config) => {
      const requestId = config.headers?.['X-Request-Id']
      expect(requestId).toBeTruthy()
      expect(String(requestId)).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/i)
      return [200, { ok: true }]
    })

    await client.get('/health')
    mock.restore()
  })

  it('maps API error envelope to AppError', async () => {
    const client = createHttpClient()
    const mock = new MockAdapter(client)
    mock.onGet('/fail').reply(422, {
      error: {
        code: 'validation_error',
        message: "Field 'email' is required",
        details: { field: 'email' },
        request_id: '01JTEST',
      },
    })

    await expect(client.get('/fail')).rejects.toMatchObject({
      name: 'AppError',
      code: 'validation_error',
      message: "Field 'email' is required",
      requestId: '01JTEST',
      status: 422,
    })

    mock.restore()
  })

  it('falls back to internal_error for non-JSON errors', async () => {
    const client = createHttpClient()
    const mock = new MockAdapter(client)
    mock.onGet('/broken').reply(500, 'upstream failure')

    try {
      await client.get('/broken')
      expect.unreachable('should throw')
    } catch (err) {
      expect(err).toBeInstanceOf(AppError)
      expect((err as AppError).code).toBe('internal_error')
      expect((err as AppError).status).toBe(500)
    }

    mock.restore()
  })
})
