import api from '@/api'
import type { CreditLedgerResponse } from '@/types/creditLedger'

interface CreditLedgerParams {
  page?: number
  page_size?: number
}

export async function getCurrentUserCreditLedger(
  params: CreditLedgerParams = {},
): Promise<CreditLedgerResponse> {
  const response = await api.get<CreditLedgerResponse>('/users/me/credits/ledger', {
    params,
  })
  return response.data
}
