// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchStats: vi.fn(),
  fetchStatsHistory: vi.fn(),
  fetchFinanceStats: vi.fn(),
  fetchFinanceHistory: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

import { useDashboardOverview } from './useDashboardOverview'

describe('useDashboardOverview focused refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchStats.mockResolvedValue({ total_users: 10 })
    apiMocks.fetchStatsHistory.mockResolvedValue([{ date: '2026-08-31' }])
    apiMocks.fetchFinanceStats.mockResolvedValue({ rmb_balance: 88 })
    apiMocks.fetchFinanceHistory.mockResolvedValue([{ date: '2026-08-31', rmb_recharge: 8 }])
  })

  it('refreshes the finance page without scanning global dashboard statistics', async () => {
    const overview = useDashboardOverview()

    await overview.refreshData('finance')

    expect(apiMocks.fetchFinanceStats).toHaveBeenCalledOnce()
    expect(apiMocks.fetchFinanceHistory).toHaveBeenCalledWith(7)
    expect(apiMocks.fetchStats).not.toHaveBeenCalled()
    expect(apiMocks.fetchStatsHistory).not.toHaveBeenCalled()
    expect(overview.financeStats.value.rmb_balance).toBe(88)
  })
})
