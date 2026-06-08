import { describe, expect, it } from 'vitest'
import { shouldBypassDashboardCache } from './client'

describe('shouldBypassDashboardCache', () => {
  it('keeps cacheable dashboard summary endpoints cacheable', () => {
    expect(shouldBypassDashboardCache('/api/stats')).toBe(false)
    expect(shouldBypassDashboardCache('/api/stats/history?days=30')).toBe(false)
    expect(shouldBypassDashboardCache('/api/system/status')).toBe(false)
    expect(shouldBypassDashboardCache('/api/system/workers')).toBe(false)
    expect(shouldBypassDashboardCache('/api/system/concurrency_stats')).toBe(false)
  })

  it('bypasses cache for management and user-specific endpoints', () => {
    expect(shouldBypassDashboardCache('/api/auth/login')).toBe(true)
    expect(shouldBypassDashboardCache('/api/users?limit=20')).toBe(true)
    expect(shouldBypassDashboardCache('/api/system/active_bot_tasks')).toBe(true)
    expect(shouldBypassDashboardCache('/api/system/clean_zombie_tasks')).toBe(true)
  })
})
