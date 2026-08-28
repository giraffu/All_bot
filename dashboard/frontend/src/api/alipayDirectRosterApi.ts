import { api, appendQueryParam, unwrapData, withQuery } from './client'

export interface AlipayDirectRosterFilters {
  page?: number
  pageSize?: number
  minPaidCount?: number | null
  maxPaidCount?: number | null
  firstUsedFrom?: string | null
  firstUsedTo?: string | null
  directPaid?: boolean | null
  enabled?: boolean | null
  query?: string | null
  sortBy?: 'created_at' | 'paid_count' | 'direct_paid_count' | 'id'
  sortOrder?: 'asc' | 'desc'
}

export interface AlipayDirectRosterItem {
  id: number
  username: string | null
  full_name: string | null
  created_at: string | null
  alipay_direct_enabled: boolean
  paid_count: number
  direct_paid_count: number
  has_direct_paid: boolean
  last_direct_paid_at: string | null
}

export interface AlipayDirectRosterResponse {
  items: AlipayDirectRosterItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface AlipayDirectBulkFilters {
  min_paid_count?: number | null
  max_paid_count?: number | null
  first_used_from?: string | null
  first_used_to?: string | null
  direct_paid?: boolean | null
  enabled?: boolean | null
  query?: string | null
}

export type AlipayDirectBulkRequest =
  | {
      enabled: boolean
      selection_mode: 'ids'
      user_ids: number[]
    }
  | {
      enabled: boolean
      selection_mode: 'filters'
      filters: AlipayDirectBulkFilters
    }

export interface AlipayDirectBulkResponse {
  status: 'ok'
  enabled: boolean
  matched_count: number
  updated_count: number
}

export const fetchAlipayDirectRoster = async (
  filters: AlipayDirectRosterFilters = {},
): Promise<AlipayDirectRosterResponse> => {
  const url = withQuery('/api/alipay-direct-users', (params: URLSearchParams) => {
    appendQueryParam(params, 'page', filters.page ?? 1)
    appendQueryParam(params, 'page_size', filters.pageSize ?? 20)
    appendQueryParam(params, 'min_paid_count', filters.minPaidCount)
    appendQueryParam(params, 'max_paid_count', filters.maxPaidCount)
    appendQueryParam(params, 'first_used_from', filters.firstUsedFrom)
    appendQueryParam(params, 'first_used_to', filters.firstUsedTo)
    appendQueryParam(params, 'direct_paid', filters.directPaid)
    appendQueryParam(params, 'enabled', filters.enabled)
    appendQueryParam(params, 'query', filters.query)
    appendQueryParam(params, 'sort_by', filters.sortBy ?? 'created_at')
    appendQueryParam(params, 'sort_order', filters.sortOrder ?? 'desc')
  })
  return api.get(url).then(unwrapData)
}

export const bulkUpdateAlipayDirectRoster = async (
  request: AlipayDirectBulkRequest,
): Promise<AlipayDirectBulkResponse> =>
  api.post('/api/alipay-direct-users/bulk-status', request).then(unwrapData)
