import { computed, type Ref } from 'vue'
import {
  resolveMediaDetailView,
  type MediaCardLike,
  type MediaCardViewOptions
} from '@/utils/mediaCardView'

export function useCurrentDetailMedia<TPost extends MediaCardLike>(
  currentPost: Ref<TPost | null>,
  options: MediaCardViewOptions = {}
) {
  return computed(() => {
    if (!currentPost.value) {
      return null
    }

    return resolveMediaDetailView(currentPost.value, options)
  })
}
