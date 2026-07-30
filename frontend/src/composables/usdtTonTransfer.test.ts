import { Address, Cell } from '@ton/core'
import { describe, expect, it } from 'vitest'

import {
  OFFICIAL_USDT_TON_MASTER_ADDRESS,
  buildUsdtTonTransferMessage,
} from './usdtTonTransfer'

const MERCHANT_ADDRESS = 'UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ'
const PAYER_ADDRESS = 'UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ'

describe('USDT-TON transfer contract', () => {
  it('builds an official six-decimal USDT Jetton transfer with the order comment', () => {
    const message = buildUsdtTonTransferMessage({
      usdt_receiver_address: MERCHANT_ADDRESS,
      usdt_jetton_master_address: OFFICIAL_USDT_TON_MASTER_ADDRESS,
      amount_microusdt: '4500000',
      usdt_comment: 'ORDER_V2:bo_usdt_ton_1',
    }, PAYER_ADDRESS, 42n)

    expect(message.amount).toBe('50000000')
    expect(Address.parse(message.address)).toBeTruthy()

    const slice = Cell.fromBase64(message.payload).beginParse()
    expect(slice.loadUint(32)).toBe(0x0f8a7ea5)
    expect(slice.loadUintBig(64)).toBe(42n)
    expect(slice.loadCoins()).toBe(4_500_000n)
    expect(slice.loadAddress().equals(Address.parse(MERCHANT_ADDRESS))).toBe(true)
    expect(slice.loadAddress().equals(Address.parse(PAYER_ADDRESS))).toBe(true)
    expect(slice.loadBit()).toBe(false)
    expect(slice.loadCoins()).toBe(1n)
    expect(slice.loadBit()).toBe(true)

    const comment = slice.loadRef().beginParse()
    expect(comment.loadUint(32)).toBe(0)
    expect(comment.loadStringTail()).toBe('ORDER_V2:bo_usdt_ton_1')
  })

  it('rejects a server response that names a different Jetton master', () => {
    expect(() => buildUsdtTonTransferMessage({
      usdt_receiver_address: MERCHANT_ADDRESS,
      usdt_jetton_master_address: '0:' + '1'.repeat(64),
      amount_microusdt: '4500000',
      usdt_comment: 'ORDER_V2:bo_usdt_ton_1',
    }, PAYER_ADDRESS, 42n)).toThrow('invalid USDT-TON order response')
  })
})
