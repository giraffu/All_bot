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

  it('adds H3 input and chain facets without leaking them into the request config', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({
      data: { items: [], total: 0 },
    })
    const signal = new AbortController().signal

    await fetchHistoryAll(
      1,
      20,
      'minimax_h3_ref2v',
      null,
      null,
      null,
      null,
      null,
      { signal, h3InputKind: 'video', h3ChainKind: 'segment' },
    )

    expect(get).toHaveBeenCalledWith(
      '/api/history/all?page=1&page_size=20&type=minimax_h3_ref2v&h3_input_kind=video&h3_chain_kind=segment',
      { signal },
    )
  })
})
