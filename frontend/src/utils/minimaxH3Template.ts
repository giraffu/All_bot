import { MINIMAX_H3_PRICE_CONTRACT } from '@/generated/taskTypeContract'

export interface ImageDimensions {
  width: number
  height: number
}

export type MiniMaxH3PriceMode = keyof typeof MINIMAX_H3_PRICE_CONTRACT

export type MiniMaxH3PriceModifiers = {
  referenceAudio?: boolean
  referenceVideo?: boolean
}

export const getMinimaxH3Cost = (
  mode: MiniMaxH3PriceMode,
  preset: string | null,
  duration: number | null,
  modifiers: MiniMaxH3PriceModifiers = {},
): number => {
  const matrix = MINIMAX_H3_PRICE_CONTRACT[mode] as Record<string, Record<string, number>>
  const durationCosts = matrix[String(duration)] ?? matrix['5']
  const baseCost = durationCosts?.[preset || ''] ?? durationCosts?.preview ?? 0
  let numerator = baseCost
  let denominator = 1
  if (modifiers.referenceAudio) {
    numerator *= 11
    denominator *= 10
  }
  if (modifiers.referenceVideo) {
    numerator *= 8
    denominator *= 5
  }
  return Math.ceil(numerator / denominator)
}

export const areFrameAspectRatiosCompatible = (
  first: ImageDimensions,
  last: ImageDimensions,
  tolerance = 0.01,
): boolean => {
  if (first.width <= 0 || first.height <= 0 || last.width <= 0 || last.height <= 0) {
    return false
  }
  const firstRatio = first.width / first.height
  const lastRatio = last.width / last.height
  return Math.abs(lastRatio - firstRatio) / firstRatio <= tolerance
}

export const getMinimaxH3TemplateCost = (
  preset: string | null,
  duration: number | null,
  mode: MiniMaxH3PriceMode = 'normal',
  modifiers: MiniMaxH3PriceModifiers = {},
): number => {
  return getMinimaxH3Cost(mode, preset, duration, modifiers)
}

export const readImageDimensions = (file: File): Promise<ImageDimensions> => (
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      const dimensions = { width: image.naturalWidth, height: image.naturalHeight }
      URL.revokeObjectURL(url)
      resolve(dimensions)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image_dimensions_unavailable'))
    }
    image.src = url
  })
)
