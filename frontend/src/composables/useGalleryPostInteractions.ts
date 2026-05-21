import { ref } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'

type InteractionAction = 'like' | 'dislike'
type InteractionState = 'added' | 'canceled' | 'switched'

interface InteractablePost {
  id: number
  likes_count: number
  dislikes_count: number
  has_liked: boolean
  has_disliked: boolean
}

interface UseGalleryPostInteractionsOptions<T extends InteractablePost> {
  resolveSuccessMessage: (
    action: InteractionAction,
    state: InteractionState
  ) => string
  shouldIgnoreError?: (error: any) => boolean
  onError?: (error: any, post: T, action: InteractionAction) => void
}

export function useGalleryPostInteractions<T extends InteractablePost>(
  options: UseGalleryPostInteractionsOptions<T>
) {
  const interactingPosts = ref<Record<number, boolean>>({})

  const handleInteract = async (post: T, action: InteractionAction) => {
    if (interactingPosts.value[post.id]) return

    interactingPosts.value[post.id] = true
    try {
      const { data: resData } = await api.post(`/gallery/posts/${post.id}/interact`, null, {
        params: { action },
      })

      const result = resData.data
      const actionState = result.action_state as InteractionState

      post.likes_count = result.likes_count
      post.dislikes_count = result.dislikes_count

      if (actionState === 'added') {
        if (action === 'like') post.has_liked = true
        else post.has_disliked = true
      } else if (actionState === 'canceled') {
        if (action === 'like') post.has_liked = false
        else post.has_disliked = false
      } else if (actionState === 'switched') {
        if (action === 'like') {
          post.has_liked = true
          post.has_disliked = false
        } else {
          post.has_disliked = true
          post.has_liked = false
        }
      }

      message.success(options.resolveSuccessMessage(action, actionState))
    } catch (error: any) {
      if (options.shouldIgnoreError?.(error)) {
        return
      }
      options.onError?.(error, post, action)
    } finally {
      interactingPosts.value[post.id] = false
    }
  }

  return {
    interactingPosts,
    handleInteract,
  }
}
