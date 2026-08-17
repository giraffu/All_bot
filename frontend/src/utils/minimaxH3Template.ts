export interface ImageDimensions {
  width: number
  height: number
}

const COST_BY_PRESET: Record<string, number> = {
  preview: 10,
  small: 15,
  standard: 20,
  hd: 30,
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

export const getMinimaxH3TemplateCost = (preset: string | null, duration: number | null): number => {
  const baseCost = COST_BY_PRESET[preset || ''] ?? COST_BY_PRESET.preview
  const multiplier = duration === 10 ? 2 : duration === 15 ? 3 : 1
  return baseCost * multiplier
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
