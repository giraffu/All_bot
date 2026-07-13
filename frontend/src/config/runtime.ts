export type RuntimeConfigValue = string | boolean

export type AllBotRuntimeConfig = Record<string, RuntimeConfigValue | undefined>

declare global {
  interface Window {
    __ALLBOT_CONFIG__?: AllBotRuntimeConfig
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
