import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCurrentUserCreditLedger } from '@/api/creditLedger'

const { apiGetMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock,
  },
}))

describe('creditLedger api', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
  })

  it('requests the current user credit ledger with pagination params', async () => {
    const expected = {
      items: [],
      total: 0,
      page: 2,
      page_size: 20,
      total_pages: 0,
    }
    apiGetMock.mockResolvedValue({ data: expected })

    const response = await getCurrentUserCreditLedger({ page: 2, page_size: 20 })

    expect(response).toBe(expected)
    expect(apiGetMock).toHaveBeenCalledWith('/users/me/credits/ledger', {
      params: { page: 2, page_size: 20 },
    })
  })
})
