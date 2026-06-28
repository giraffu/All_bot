import { computed, ref, type Ref } from 'vue'
import type { GalleryTaskTypeOption } from '@/composables/useGalleryConfig'
import {
  GALLERY_EDIT_GROUP_TASK_TYPE,
  GALLERY_IMG2VIDEO_GROUP_TASK_TYPE,
  GALLERY_LORA_MODEL_NONE,
  isGalleryGroupedTaskType,
} from '@/utils/galleryTaskTypeFilters'

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

  const currentLoraModels = computed(() => {
    if (taskType.value === GALLERY_EDIT_GROUP_TASK_TYPE) {
      return options.img2imgLoraModels.value
    }
    if (taskType.value === GALLERY_IMG2VIDEO_GROUP_TASK_TYPE) {
      return options.videoLoraModels.value
    }
    return []
  })

  const hasAddonSubfilters = computed(() => (
    isGalleryGroupedTaskType(taskType.value) && currentLoraModels.value.length > 0
  ))

  const requestLoraModel = computed(() => {
    if (!hasAddonSubfilters.value || loraModel.value === 'all') {
      return undefined
    }
    if (loraModel.value === GALLERY_LORA_MODEL_NONE) {
      return GALLERY_LORA_MODEL_NONE
    }
    return loraModel.value
  })

  const triggerReload = () => {
    options.onFiltersChange()
  }

  const handleTaskTypeChange = (type: string) => {
    if (taskType.value === type) {
      return
    }

    taskType.value = type
    loraModel.value = 'all'
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
    hasAddonSubfilters,
    currentLoraModels,
    requestLoraModel,
    handleTaskTypeChange,
    handleTimeRangeChange,
    handleSortChange,
    handleLoraModelChange,
  }
}
