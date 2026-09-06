import { afterEach, describe, expect, it, vi } from 'vitest'

import api, { configureApiRuntime } from './index'

vi.mock('ant-design-vue', () => ({
  message: {
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

const originalAdapter = api.defaults.adapter

afterEach(() => {
  api.defaults.adapter = originalAdapter
  configureApiRuntime({
    getToken: () => null,
    handleUnauthorized: () => undefined,
    getCurrentPath: () => '',
    navigate: () => undefined,
  })
})

describe('API runtime adapter', () => {
  it('reads the current token without importing the auth store', async () => {
    let authorization: unknown
    configureApiRuntime({
      getToken: () => 'runtime-token',
      handleUnauthorized: () => undefined,
      getCurrentPath: () => '/',
      navigate: () => undefined,
    })
    api.defaults.adapter = async (config) => {
      authorization = config.headers?.Authorization
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await api.get('/health')

    expect(authorization).toBe('Bearer runtime-token')
  })

  it('delegates an unhandled 401 to the configured session boundary', async () => {
    const handleUnauthorized = vi.fn()
    const navigate = vi.fn()
    configureApiRuntime({
      getToken: () => 'expired-token',
      handleUnauthorized,
      getCurrentPath: () => '/',
      navigate,
    })
    api.defaults.adapter = async (config) => Promise.reject({
      config,
      response: { status: 401, data: {} },
    })

    await expect(api.get('/users/me')).rejects.toBeDefined()

    expect(handleUnauthorized).toHaveBeenCalledOnce()
    expect(navigate).toHaveBeenCalledWith('/login')
  })
})
