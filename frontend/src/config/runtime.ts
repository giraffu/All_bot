export type RuntimeConfigValue = string | boolean

export type AllBotRuntimeConfig = Record<string, RuntimeConfigValue | undefined>

export interface RuntimeTaskPricingVariant {
  variant_id: string
  task_types: string[]
  conditions: Record<string, string>
}

export interface RuntimeTaskPricingCatalog {
  prices: Readonly<Record<string, number>>
  variants: readonly RuntimeTaskPricingVariant[]
}

declare global {
  interface Window {
    __ALLBOT_CONFIG__?: AllBotRuntimeConfig
    __ALLBOT_TASK_PRICE_OVERRIDES__?: Readonly<Record<string, number>>
    __ALLBOT_TASK_PRICING__?: RuntimeTaskPricingCatalog
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

export const getRuntimeTaskPrice = (
  taskType: string,
  fallback: number,
  conditions: Record<string, string | number | boolean> = {},
): number => {
  if (typeof window === 'undefined') return fallback
  const pricing = window.__ALLBOT_TASK_PRICING__
  if (pricing) {
    const normalizedConditions = Object.fromEntries(
      Object.entries(conditions).map(([key, value]) => [
        key,
        typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value),
      ]),
    )
    const matches = pricing.variants.filter(variant => (
      variant.task_types.includes(taskType)
      && Object.entries(variant.conditions).every(
        ([key, value]) => normalizedConditions[key] === value,
      )
    ))
    if (matches.length === 1) {
      const configured = pricing.prices[matches[0].variant_id]
      if (typeof configured === 'number' && Number.isInteger(configured) && configured >= 0) {
        return configured
      }
    }
  }
  const value = window.__ALLBOT_TASK_PRICE_OVERRIDES__?.[taskType]
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : fallback
}
