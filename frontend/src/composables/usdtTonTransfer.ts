import { Address, Cell, beginCell, contractAddress } from '@ton/core'

export const OFFICIAL_USDT_TON_MASTER_ADDRESS =
  'EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs'
export const USDT_TON_TRANSFER_GAS_NANOTONS = '50000000'

const USDT_JETTON_WALLET_CODE = Cell.fromHex(
  'b5ee9c72010101010023000842028f452d7a4dfd74066b682365177259ed05734435be76b5fd4bd5d8af2b7c3d68',
)

type UsdtTonOrder = {
  usdt_receiver_address?: string | null
  usdt_jetton_master_address?: string | null
  amount_microusdt?: string | null
  usdt_comment?: string | null
}

const parsePositiveInteger = (value: string | null | undefined) => {
  if (!value || !/^[1-9]\d*$/.test(value)) {
    throw new Error('invalid USDT-TON order response')
  }
  return BigInt(value)
}

const sameAddress = (left: Address, right: Address) => left.equals(right)

export const deriveUsdtJettonWalletAddress = (
  ownerAddress: Address,
  masterAddress: Address,
) => {
  const data = beginCell()
    .storeAddress(ownerAddress)
    .storeAddress(masterAddress)
    .storeVarUint(0, 16)
    .endCell()

  return contractAddress(0, {
    code: USDT_JETTON_WALLET_CODE,
    data,
  })
}

export const buildUsdtTonTransferMessage = (
  order: UsdtTonOrder,
  payerWalletAddress: string,
  queryId: bigint = BigInt(Date.now()),
) => {
  try {
    const receiver = Address.parse(String(order.usdt_receiver_address || ''))
    const payer = Address.parse(payerWalletAddress)
    const master = Address.parse(String(order.usdt_jetton_master_address || ''))
    const officialMaster = Address.parse(OFFICIAL_USDT_TON_MASTER_ADDRESS)
    const amount = parsePositiveInteger(order.amount_microusdt)
    const commentText = String(order.usdt_comment || '').trim()
    if (!sameAddress(master, officialMaster) || !commentText.startsWith('ORDER')) {
      throw new Error('invalid USDT-TON order response')
    }

    const forwardPayload = beginCell()
      .storeUint(0, 32)
      .storeStringTail(commentText)
      .endCell()
    const transferPayload = beginCell()
      .storeUint(0x0f8a7ea5, 32)
      .storeUint(queryId, 64)
      .storeCoins(amount)
      .storeAddress(receiver)
      .storeAddress(payer)
      .storeBit(false)
      .storeCoins(1)
      .storeBit(true)
      .storeRef(forwardPayload)
      .endCell()

    return {
      address: deriveUsdtJettonWalletAddress(payer, master).toString({
        bounceable: true,
        urlSafe: true,
      }),
      amount: USDT_TON_TRANSFER_GAS_NANOTONS,
      payload: transferPayload.toBoc().toString('base64'),
    }
  } catch {
    throw new Error('invalid USDT-TON order response')
  }
}
