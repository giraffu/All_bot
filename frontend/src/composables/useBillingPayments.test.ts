// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildUsdtTonConfirmationDetails,
  buildTonTransactionMessage,
  filterPlansForBillingKind,
  hasTelegramExternalLinkOpener,
  openExternalPaymentUrl,
  resolveBillingEntry,
  resolveTonPaymentAvailability,
  resolveUsdtTonPaymentAvailability,
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
  it('keeps native TON and USDT-TON availability independent', () => {
    const data = {
      ton_payment_enabled: true,
      ton_receiver_address: 'UQnative-ton-merchant',
      usdt_ton_payment_enabled: false,
      usdt_ton_receiver_address: 'UQusdt-ton-merchant',
      usdt_ton_jetton_master_address: 'EQofficial-usdt-master',
    }

    expect(resolveTonPaymentAvailability(data)).toEqual({
      enabled: true,
      receiverAddress: 'UQnative-ton-merchant',
    })
    expect(resolveUsdtTonPaymentAvailability(data)).toEqual({
      enabled: false,
      receiverAddress: null,
      jettonMasterAddress: null,
    })
  })

  it('builds an explicit USDT-TON confirmation before opening the wallet', () => {
    expect(buildUsdtTonConfirmationDetails({
      amount_usdt: 10,
      usdt_receiver_address: 'UQusdt-ton-merchant',
    })).toEqual({
      amount: '10 USDT',
      network: 'TON',
      receiverAddress: 'UQusdt-ton-merchant',
      maxGas: '0.05 TON',
    })
  })

  it('resolves the Bot TON deep link and filters membership plans', () => {
    const entry = resolveBillingEntry({ method: 'ton', kind: 'membership' })
    const plans = [
      { id: 1, duration_days: 30 },
      { id: 5, duration_days: 0 },
    ]

    expect(entry).toEqual({ method: 'ton', kind: 'membership' })
    expect(filterPlansForBillingKind(plans, entry.kind)).toEqual([plans[0]])
  })

  it('resolves the Bot USDT-TON deep link and filters credit plans', () => {
    const entry = resolveBillingEntry({ method: 'usdt-ton', kind: 'credits' })
    const plans = [
      { id: 1, duration_days: 30 },
      { id: 5, duration_days: 0 },
    ]

    expect(entry).toEqual({ method: 'usdt-ton', kind: 'credits' })
    expect(filterPlansForBillingKind(plans, entry.kind)).toEqual([plans[1]])
  })

  it('falls back to the complete billing page for invalid entry params', () => {
    expect(resolveBillingEntry({ method: 'crypto', kind: 'membership' })).toEqual({
      method: 'alipay',
      kind: null,
    })
  })

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
