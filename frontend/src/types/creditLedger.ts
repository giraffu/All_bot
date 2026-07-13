export type CreditLedgerDirection = 'income' | 'expense'

export type CreditLedgerDisplayContext = Record<string, string | number | boolean>

export interface CreditLedgerItem {
  id: number
  operation_type: string
  direction: CreditLedgerDirection
  credit_change: number
  current_balance: number
  created_at: string
  display_context: CreditLedgerDisplayContext
}

export interface CreditLedgerResponse {
  items: CreditLedgerItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
