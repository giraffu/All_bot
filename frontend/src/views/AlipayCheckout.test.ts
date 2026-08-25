// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, toDataURL } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  toDataURL: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: { get: apiGet },
}))

vi.mock('qrcode', () => ({
  default: { toDataURL },
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { token: 'checkout-token' } }),
  }
})

import i18n from '@/i18n'
import AlipayCheckout from '@/views/AlipayCheckout.vue'


describe('AlipayCheckout', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGet.mockReset()
    toDataURL.mockReset()
    apiGet.mockResolvedValue({
      data: {
        data: {
          order_id: 'bo_public_1',
          subject: '内门弟子（30天）',
          amount: '30.00',
          status: 'PENDING',
          created_at: '2026-08-25T12:40:17+00:00',
        },
      },
    })
    toDataURL.mockResolvedValue('data:image/png;base64,qr-image')
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('renders one responsive checkout with a QR and mobile launch action', async () => {
    const wrapper = mount(AlipayCheckout, {
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const expectedLaunch = new URL(
      '/api/payment/alipay-checkout/checkout-token/launch',
      window.location.origin,
    ).toString()
    expect(toDataURL).toHaveBeenCalledWith(expectedLaunch, expect.objectContaining({
      errorCorrectionLevel: 'M',
    }))
    expect(wrapper.get('[data-testid="checkout-order"]').text()).toContain('bo_public_1')
    expect(wrapper.get('[data-testid="checkout-amount"]').text()).toBe('¥30.00')
    expect(wrapper.get('[data-testid="checkout-qr"]').attributes('src')).toBe(
      'data:image/png;base64,qr-image',
    )
    expect(wrapper.get('[data-testid="checkout-launch"]').attributes('href')).toBe(
      expectedLaunch,
    )
    wrapper.unmount()
  })

  it('changes to the paid state when status polling observes success', async () => {
    apiGet
      .mockResolvedValueOnce({
        data: { data: {
          order_id: 'bo_public_1', subject: 'Plan', amount: '30.00',
          status: 'PENDING', created_at: '2026-08-25T12:40:17+00:00',
        } },
      })
      .mockResolvedValueOnce({
        data: { data: {
          order_id: 'bo_public_1', subject: 'Plan', amount: '30.00',
          status: 'SUCCESS', created_at: '2026-08-25T12:40:17+00:00',
        } },
      })

    const wrapper = mount(AlipayCheckout, {
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(wrapper.find('[data-testid="checkout-success"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="checkout-launch"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('fails closed without a launch action for a failed order', async () => {
    apiGet.mockResolvedValueOnce({
      data: { data: {
        order_id: 'bo_public_1', subject: 'Plan', amount: '30.00',
        status: 'FAILED', created_at: '2026-08-25T12:40:17+00:00',
      } },
    })

    const wrapper = mount(AlipayCheckout, {
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('暂时无法打开支付订单')
    expect(wrapper.find('[data-testid="checkout-launch"]').exists()).toBe(false)
    expect(toDataURL).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
