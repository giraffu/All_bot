import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchHistoryAll } from './api'
import { api } from './client'

describe('fetchHistoryAll', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('adds the username filter to the history request', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({
      data: { items: [], total: 0 },
    })

    await fetchHistoryAll(1, 20, null, null, null, null, null, 'Gray')

    expect(get).toHaveBeenCalledWith('/api/history/all?page=1&page_size=20&username=Gray', {})
  })
})
