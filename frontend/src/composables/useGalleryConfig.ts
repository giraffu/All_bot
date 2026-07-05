import { ref } from 'vue'
import api from '@/api'
import { filterVisibleGalleryTaskTypes } from '@/utils/galleryTaskTypeFilters'

export interface GalleryTaskTypeOption {
  id: string
  name: string
}

interface UseGalleryConfigOptions {
  includeLoraModels?: boolean
  onError?: (error: unknown) => void
}

export function useGalleryConfig(options: UseGalleryConfigOptions = {}) {
  const allowedTypes = ref<GalleryTaskTypeOption[]>([])
  const videoLoraModels = ref<GalleryTaskTypeOption[]>([])
  const img2imgLoraModels = ref<GalleryTaskTypeOption[]>([])

  let configPromise: Promise<void> | null = null

  const loadConfig = async () => {
    if (configPromise) return configPromise

    configPromise = (async () => {
      try {
        const res = await api.get('/gallery/config')
        allowedTypes.value = filterVisibleGalleryTaskTypes(res.data.allowed_types || [])

        if (options.includeLoraModels) {
          videoLoraModels.value = (res.data.lora_models || []).filter(
            (item: GalleryTaskTypeOption) => Boolean(item?.id)
          )
          img2imgLoraModels.value = (res.data.img2img_lora_models || []).filter(
            (item: GalleryTaskTypeOption) => Boolean(item?.id)
          )
        }
      } catch (error) {
        options.onError?.(error)
      } finally {
        configPromise = null
      }
    })()

    return configPromise
  }

  return {
    allowedTypes,
    videoLoraModels,
    img2imgLoraModels,
    loadConfig,
  }
}
