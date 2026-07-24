export const HISTORY_SOURCE_OPTIONS = [
  { label: '全部来源', value: null },
  { label: '主 Bot', value: 'bot' },
  { label: '官方懒人 Bot', value: 'bot:qqcc' },
  { label: '用户私有懒人 Bot', value: 'bot:qqcc-private' },
  { label: 'Web', value: 'web' },
] as const

export const getHistorySourceLabel = (source?: string | null): string => {
  if (source === 'web') return 'Web'
  if (source === 'bot:qqcc') return '官方懒人 Bot'
  if (source?.startsWith('bot:qqcc-private:')) {
    return `私有懒人 Bot #${source.slice('bot:qqcc-private:'.length)}`
  }
  return '主 Bot'
}

export const getHistorySourceColor = (source?: string | null): string => {
  if (source === 'web') return 'green'
  if (source === 'bot:qqcc') return 'blue'
  if (source?.startsWith('bot:qqcc-private:')) return 'purple'
  return 'orange'
}
