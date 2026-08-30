// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RmbChannelSummary from './RmbChannelSummary.vue'

describe('RmbChannelSummary', () => {
  it('shows the three active RMB rails and labels unclassified history honestly', () => {
    const wrapper = mount(RmbChannelSummary, {
      props: {
        total: 100,
        channels: {
          direct_alipay: { amount: 40, orders: 2 },
          collected_alipay: { amount: 30, orders: 3 },
          collected_wechat: { amount: 20, orders: 4 },
          legacy_unclassified: { amount: 10, orders: 1 },
        },
      },
    })

    expect(wrapper.text()).toContain('支付宝直连')
    expect(wrapper.text()).toContain('代收 · 支付宝')
    expect(wrapper.text()).toContain('代收 · 微信')
    expect(wrapper.text()).toContain('历史未区分 ¥10.00')
    expect(wrapper.findAll('[data-testid="rmb-channel-card"]')).toHaveLength(3)
  })
})
