import { describe, expect, it } from 'vitest'

import { buildHistoryInputMedia } from './historyInputMedia'


describe('buildHistoryInputMedia', () => {
  it('renders every persisted H3 reference image with an explicit label', () => {
    expect(buildHistoryInputMedia({
      type: 'minimax_h3_ref2v',
      input_file: 'source.png|reference-a.png|reference-b.png',
      input_file_url: 'url://source|url://reference-a|url://reference-b',
      input_file_preview_url: 'preview://source|preview://reference-a|preview://reference-b',
    })).toEqual([
      {
        file: 'source.png',
        url: 'url://source',
        previewUrl: 'preview://source',
        label: '参考图 1',
      },
      {
        file: 'reference-a.png',
        url: 'url://reference-a',
        previewUrl: 'preview://reference-a',
        label: '参考图 2',
      },
      {
        file: 'reference-b.png',
        url: 'url://reference-b',
        previewUrl: 'preview://reference-b',
        label: '参考图 3',
      },
    ])
  })

  it('keeps persisted inputs visible when one generated URL is missing', () => {
    const result = buildHistoryInputMedia({
      type: 'minimax_h3_ref2v',
      input_file: 'reference-a.png|reference-b.png',
      input_file_url: 'url://reference-a',
    })

    expect(result).toHaveLength(2)
    expect(result[1]).toMatchObject({
      file: 'reference-b.png',
      url: '',
      label: '参考图 2',
    })
  })
})
