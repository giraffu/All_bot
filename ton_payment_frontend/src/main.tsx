import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const TonPaymentShell = lazy(() => import('./TonPaymentShell'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<div>加载中...</div>}>
      <TonPaymentShell />
    </Suspense>
  </StrictMode>,
)
