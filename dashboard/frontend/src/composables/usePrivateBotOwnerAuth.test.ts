// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearPrivateBotOwnerToken,
  getPrivateBotOwnerToken,
  setPrivateBotOwnerToken,
} from './usePrivateBotOwnerAuth'

describe('usePrivateBotOwnerAuth', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('stores the owner JWT only in sessionStorage and clears it on logout', () => {
    setPrivateBotOwnerToken('owner-jwt')

    expect(getPrivateBotOwnerToken()).toBe('owner-jwt')
    expect(window.sessionStorage.getItem('qqcc_private_bot_owner_token')).toBe('owner-jwt')
    expect(window.localStorage.length).toBe(0)

    clearPrivateBotOwnerToken()

    expect(getPrivateBotOwnerToken()).toBeNull()
  })
})
