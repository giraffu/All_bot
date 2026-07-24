import { describe, expect, it } from 'vitest'

import {
  HISTORY_SOURCE_OPTIONS,
  getHistorySourceColor,
  getHistorySourceLabel,
} from './historySources'

describe('history source presentation', () => {
  it('offers main, official QQCC, private QQCC and web filters', () => {
    expect(HISTORY_SOURCE_OPTIONS).toEqual([
      { label: '全部来源', value: null },
      { label: '主 Bot', value: 'bot' },
      { label: '官方懒人 Bot', value: 'bot:qqcc' },
      { label: '用户私有懒人 Bot', value: 'bot:qqcc-private' },
      { label: 'Web', value: 'web' },
    ])
  })

  it('keeps the private bot id visible in the source label', () => {
    expect(getHistorySourceLabel('bot:qqcc')).toBe('官方懒人 Bot')
    expect(getHistorySourceLabel('bot:qqcc-private:17')).toBe(
      '私有懒人 Bot #17',
    )
    expect(getHistorySourceColor('bot:qqcc-private:17')).toBe('purple')
  })
})
