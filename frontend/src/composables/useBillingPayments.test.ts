// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildTonTransactionMessage,
  hasTelegramExternalLinkOpener,
  openExternalPaymentUrl,
  resolveTonPaymentAvailability,
} from './useBillingPayments'

const setTelegramWebApp = (webApp?: unknown) => {
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    value: webApp ? { WebApp: webApp } : undefined,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  setTelegramWebApp()
})

describe('openExternalPaymentUrl', () => {
  it('uses Telegram WebApp openLink when available', () => {
    const openLink = vi.fn()
    const windowOpenSpy = vi.spyOn(window, 'open')
    setTelegramWebApp({ openLink })

    expect(hasTelegramExternalLinkOpener()).toBe(true)

    openExternalPaymentUrl('https://pay.example/order')

    expect(openLink).toHaveBeenCalledWith('https://pay.example/order', {
      try_instant_view: false,
    })
    expect(windowOpenSpy).not.toHaveBeenCalled()
  })

  it('navigates a preopened browser window outside Telegram', () => {
    const windowOpenSpy = vi.spyOn(window, 'open')
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { href: 'about:blank' },
    } as unknown as Window

    openExternalPaymentUrl('https://pay.example/order', popup)

    expect(popup.location.href).toBe('https://pay.example/order')
    expect(windowOpenSpy).not.toHaveBeenCalled()
  })

  it('falls back to the preopened window if Telegram openLink throws', () => {
    const openLink = vi.fn(() => {
      throw new Error('blocked')
    })
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { href: 'about:blank' },
    } as unknown as Window
    setTelegramWebApp({ openLink })

    openExternalPaymentUrl('https://pay.example/order', popup)

    expect(consoleWarnSpy).toHaveBeenCalled()
    expect(popup.location.href).toBe('https://pay.example/order')
  })
})

describe('TON payment contract', () => {
  it('treats a disabled plans response as unavailable', () => {
    expect(resolveTonPaymentAvailability({
      ton_payment_enabled: false,
      ton_receiver_address: 'UQlegacy-frontend-fallback',
    })).toEqual({ enabled: false, receiverAddress: null })
  })

  it('rejects an order that does not include a receiver address', () => {
    expect(() => buildTonTransactionMessage({
      ton_receiver_address: null,
      amount_nanotons: '1000000000',
    }, 'payload')).toThrow('invalid TON order response')
  })

  it('uses the server order address as the only transaction address', () => {
    const message = buildTonTransactionMessage({
      ton_receiver_address: 'UQserver-order-address',
      amount_nanotons: '1000000000',
    }, 'payload')

    expect(message.address).toBe('UQserver-order-address')
    expect(message.amount).toBe('1000000000')
    expect(message.payload).toBe('payload')
  })
})
