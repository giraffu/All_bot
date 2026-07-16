export type TranslateTaskLabel = (key: string) => string
export type HasTaskLabel = (key: string) => boolean

export const resolveTaskTypeLabel = (
  rawType: string | number | null | undefined,
  t: TranslateTaskLabel,
  te: HasTaskLabel,
): string => {
  const normalized = String(rawType ?? '').trim().replace(/-/g, '_')
  const key = `task_type.${normalized}`
  return normalized && te(key) ? t(key) : t('task_type.other')
}
