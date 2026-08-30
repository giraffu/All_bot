// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchFinanceHistory: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

import FinanceDashboard from './FinanceDashboard.vue'

describe('FinanceDashboard loading', () => {
  it('waits for the parent focused history request instead of duplicating it on mount', () => {
    mount(FinanceDashboard, {
      props: {
        stats: {},
        statsHistory: [],
        historyTimeRange: 7,
        timeRangeOptions: [{ label: '最近 7 天', value: 7 }],
      },
      global: {
        stubs: {
          StatsCards: true,
          LineChart: true,
          FinanceHourlyChart: true,
          RmbChannelSummary: true,
          ARadioGroup: true,
          ARadioButton: true,
        },
      },
    })

    expect(apiMocks.fetchFinanceHistory).not.toHaveBeenCalled()
  })

  it('reserves enough height for the primary finance charts and the RMB legend', () => {
    const wrapper = mount(FinanceDashboard, {
      props: {
        stats: {},
        statsHistory: [],
        historyTimeRange: 7,
        timeRangeOptions: [{ label: '最近 7 天', value: 7 }],
      },
      global: {
        stubs: {
          StatsCards: true,
          LineChart: true,
          FinanceHourlyChart: true,
          RmbChannelSummary: true,
          ARadioGroup: true,
          ARadioButton: true,
        },
      },
    })

    const primaryCharts = wrapper.findAll('.finance-history-chart')
    expect(primaryCharts).toHaveLength(3)
    expect(primaryCharts.every(chart => chart.classes().includes('h-[420px]'))).toBe(true)
    expect(wrapper.findAllComponents({ name: 'LineChart' })[2].props('reserveLegendSpace')).toBe(true)
  })
})
