export type RuntimeConfigValue = string | boolean

export type AllBotRuntimeConfig = Record<string, RuntimeConfigValue | undefined>

declare global {
  interface Window {
    __ALLBOT_CONFIG__?: AllBotRuntimeConfig
    __ALLBOT_TASK_PRICE_OVERRIDES__?: Readonly<Record<string, number>>
  }
}

export const getRuntimeConfig = <T extends RuntimeConfigValue>(
  key: string,
  fallback: T,
): T => {
  if (typeof window === 'undefined') return fallback
  const value = window.__ALLBOT_CONFIG__?.[key]
  return typeof value === typeof fallback ? (value as T) : fallback
}

export const getRuntimeFlag = (key: string, fallback: boolean): boolean =>
  getRuntimeConfig(key, fallback)

export const getRuntimeTaskPrice = (taskType: string, fallback: number): number => {
  if (typeof window === 'undefined') return fallback
  const value = window.__ALLBOT_TASK_PRICE_OVERRIDES__?.[taskType]
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : fallback
}
