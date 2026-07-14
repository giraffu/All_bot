// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest'
import { getRuntimeConfig, getRuntimeFlag } from './runtime'

describe('runtime config', () => {
  afterEach(() => {
    delete window.__ALLBOT_CONFIG__
  })

  it('prefers the release-injected configuration', () => {
    window.__ALLBOT_CONFIG__ = {
      api_base_url: 'https://api-test.example.com/api',
      enable_free_edit_v3: false,
    }

    expect(getRuntimeConfig('api_base_url', '/api')).toBe(
      'https://api-test.example.com/api',
    )
    expect(getRuntimeFlag('enable_free_edit_v3', true)).toBe(false)
  })

  it('uses safe local defaults when no release config exists', () => {
    expect(getRuntimeConfig('api_base_url', '/api')).toBe('/api')
    expect(getRuntimeFlag('enable_free_edit_v3', true)).toBe(true)
  })
})
