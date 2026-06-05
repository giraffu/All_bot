import { TonConnectButton, TonConnectUIProvider, useTonConnectUI, useTonWallet } from '@tonconnect/ui-react'
import { beginCell } from '@ton/core'
import App from './App'

const TON_CONNECT_MANIFEST_URL = 'https://pay.aivison.it.com/tonconnect-manifest.json'

function TonPaymentRuntimeApp() {
  const wallet = useTonWallet()
  const [tonConnectUI] = useTonConnectUI()

  return (
    <App
      tonRuntime={{
        WalletButton: TonConnectButton,
        walletConnected: Boolean(wallet),
        openWalletModal: () => {
          tonConnectUI.openModal()
        },
        buildOrderPayload: (orderId: string) => {
          const body = beginCell()
            .storeUint(0, 32)
            .storeStringTail(orderId)
            .endCell()

          return body.toBoc().toString('base64')
        },
        sendPaymentTransaction: (transaction) => tonConnectUI.sendTransaction(transaction),
      }}
    />
  )
}

export default function TonPaymentShell() {
  return (
    <TonConnectUIProvider manifestUrl={TON_CONNECT_MANIFEST_URL}>
      <TonPaymentRuntimeApp />
    </TonConnectUIProvider>
  )
}
