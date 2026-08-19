// @vitest-environment jsdom

import { AxiosHeaders } from 'axios'
import type { AxiosAdapter, AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  QqccConfigAuthExpiredError,
  isQqccConfigAuthenticated,
  setQqccConfigAuthToken,
} from '../composables/useQqccConfigAuth'
import { fetchQqccConfig, qqccConfigApi } from './qqccConfigApi'

const originalAdapter = qqccConfigApi.defaults.adapter

const responseAdapter = (
  status: number,
  data: unknown,
  contentType: string,
): AxiosAdapter => vi.fn(async config => ({
  status,
  statusText: status === 200 ? 'OK' : 'Unauthorized',
  data,
  headers: new AxiosHeaders({ 'content-type': contentType }),
  config,
  request: {},
}) as AxiosResponse)

describe('qqccConfigApi authentication expiry', () => {
  beforeEach(() => {
    window.localStorage.clear()
    setQqccConfigAuthToken('stale-token')
  })

  afterEach(() => {
    qqccConfigApi.defaults.adapter = originalAdapter
    window.localStorage.clear()
    isQqccConfigAuthenticated.value = false
  })

  it('expires the local login when the backend rejects the token', async () => {
    qqccConfigApi.defaults.adapter = responseAdapter(
      401,
      { detail: 'Could not validate credentials' },
      'application/json',
    )

    await expect(fetchQqccConfig()).rejects.toBeInstanceOf(QqccConfigAuthExpiredError)
    expect(isQqccConfigAuthenticated.value).toBe(false)
  })

  it('expires the local login when Cloudflare Access returns an HTML login page', async () => {
    qqccConfigApi.defaults.adapter = responseAdapter(
      200,
      '<!doctype html><title>Access login</title>',
      'text/html; charset=utf-8',
    )

    await expect(fetchQqccConfig()).rejects.toBeInstanceOf(QqccConfigAuthExpiredError)
    expect(isQqccConfigAuthenticated.value).toBe(false)
  })
})
