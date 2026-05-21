import { computed, ref, type Ref } from 'vue'
import type { GalleryTaskTypeOption } from '@/composables/useGalleryConfig'

interface UseGalleryFiltersOptions {
  videoLoraModels: Ref<GalleryTaskTypeOption[]>
  img2imgLoraModels: Ref<GalleryTaskTypeOption[]>
  onFiltersChange: () => void
}

export function useGalleryFilters(options: UseGalleryFiltersOptions) {
  const mediaType = ref('all')
  const taskType = ref('all')
  const loraModel = ref('all')
  const sortBy = ref('latest')
  const timeRange = ref('all')

  const isLoraTaskType = computed(
    () => taskType.value === 'video_lora' || taskType.value === 'img2img_lora'
  )

  const currentLoraModels = computed(() => {
    if (taskType.value === 'img2img_lora') {
      return options.img2imgLoraModels.value
    }
    return options.videoLoraModels.value
  })

  const triggerReload = () => {
    options.onFiltersChange()
  }

  const handleTaskTypeChange = (type: string) => {
    if (taskType.value === type) {
      return
    }

    taskType.value = type
    if (!isLoraTaskType.value) {
      loraModel.value = 'all'
    }
    triggerReload()
  }

  const handleTimeRangeChange = (nextTimeRange: string) => {
    if (timeRange.value === nextTimeRange) {
      return
    }
    timeRange.value = nextTimeRange
    triggerReload()
  }

  const handleSortChange = (nextSortBy: string) => {
    if (sortBy.value === nextSortBy) {
      return
    }
    sortBy.value = nextSortBy
    triggerReload()
  }

  const handleLoraModelChange = (nextLoraModel: string) => {
    if (loraModel.value === nextLoraModel) {
      return
    }
    loraModel.value = nextLoraModel
    triggerReload()
  }

  return {
    mediaType,
    taskType,
    loraModel,
    sortBy,
    timeRange,
    isLoraTaskType,
    currentLoraModels,
    handleTaskTypeChange,
    handleTimeRangeChange,
    handleSortChange,
    handleLoraModelChange,
  }
}
