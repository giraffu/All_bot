// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import UsdtTonConfirmationModal from './UsdtTonConfirmationModal.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => ({
      'billing.usdt_ton_confirm_title': '确认 USDT-TON 支付',
      'billing.usdt_ton_confirm_amount_label': '本次支付',
      'billing.usdt_ton_confirm_network': '网络',
      'billing.usdt_ton_confirm_receiver': '收款地址',
      'billing.usdt_ton_confirm_max_gas': '最多附带 Gas',
      'billing.usdt_ton_wallet_gas_only_notice': '部分钱包的确认页只显示外层 Gas',
      'billing.usdt_ton_open_wallet': '继续，打开钱包',
      'billing.cancel': '取消',
    }[key] || key),
  }),
}))

const mountModal = () => mount(UsdtTonConfirmationModal, {
  props: {
    open: true,
    loading: false,
    details: {
      amount: '10 USDT',
      network: 'TON',
      receiverAddress: 'UQusdt-ton-merchant',
      maxGas: '0.05 TON',
    },
  },
  global: {
    stubs: {
      'a-modal': {
        props: ['open'],
        template: '<section v-if="open"><slot /></section>',
      },
      'a-button': {
        template: '<button type="button"><slot /></button>',
      },
    },
  },
})

describe('UsdtTonConfirmationModal', () => {
  it('shows the exact asset, network, receiver, gas cap, and wallet warning', () => {
    const wrapper = mountModal()

    expect(wrapper.text()).toContain('10 USDT')
    expect(wrapper.text()).toContain('TON')
    expect(wrapper.text()).toContain('UQusdt-ton-merchant')
    expect(wrapper.text()).toContain('0.05 TON')
    expect(wrapper.text()).toContain('部分钱包的确认页只显示外层 Gas')
  })

  it('requires an explicit continue or cancel action', async () => {
    const wrapper = mountModal()
    const buttons = wrapper.findAll('button')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })
})
