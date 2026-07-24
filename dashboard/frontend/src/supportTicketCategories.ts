export const SUPPORT_TICKET_CATEGORY_OPTIONS = [
  { value: 'recharge', label: '充值问题' },
  { value: 'bug', label: 'Bug反馈' },
  { value: 'suggestion', label: '意见反馈' },
  { value: 'business', label: '商业合作' },
  { value: 'uncategorized', label: '未分类' },
] as const

const categoryLabels = Object.fromEntries(
  SUPPORT_TICKET_CATEGORY_OPTIONS.map(({ value, label }) => [value, label]),
) as Record<string, string>

export const formatSupportTicketCategory = (category: string): string =>
  categoryLabels[category] ?? `其他分类（${category || '未知'}）`
