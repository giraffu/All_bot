import { ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { unlockGalleryPrompt } from '@/api/gallery'
import { useAuthStore } from '@/stores/auth'
import type { GalleryPost } from '@/types/gallery'

interface UseGalleryPromptUnlockOptions<Post extends GalleryPost> {
  posts: Ref<Post[]>
  currentPost: Ref<Post | null>
  t: (key: string, params?: Record<string, unknown>) => string
}

export function useGalleryPromptUnlock<Post extends GalleryPost>(
  options: UseGalleryPromptUnlockOptions<Post>,
) {
  const promptUnlockingPostId = ref<number | null>(null)

  const applyUnlockedPrompt = (post: Post): Post => ({
    ...post,
    prompt_unlocked: true,
    prompt_unlockable: false,
    prompt_is_masked: false,
  })

  const handleUnlockPrompt = async (post = options.currentPost.value) => {
    if (!post || !post.prompt_unlockable) {
      return
    }

    const postId = Number(post.id)
    if (!Number.isFinite(postId) || postId <= 0) {
      return
    }

    promptUnlockingPostId.value = postId
    try {
      const result = await unlockGalleryPrompt(postId)
      const authStore = useAuthStore()
      authStore.updateBalance(result.current_credits)

      const nextCurrentPost = {
        ...post,
        prompt: result.prompt,
        prompt_unlocked: true,
        prompt_unlockable: false,
        prompt_is_masked: false,
        prompt_unlock_price: result.prompt_unlock_price,
      } as Post

      options.posts.value = options.posts.value.map((item) =>
        Number(item.id) === result.post_id
          ? applyUnlockedPrompt({
              ...item,
              prompt: result.prompt,
              prompt_unlock_price: result.prompt_unlock_price,
            } as Post)
          : item,
      )

      if (options.currentPost.value && Number(options.currentPost.value.id) === result.post_id) {
        options.currentPost.value = nextCurrentPost
      }

      message.success(
        result.already_unlocked
          ? options.t('my_notes.prompt_already_unlocked')
          : options.t('my_notes.prompt_unlock_success'),
      )
    } catch (error) {
      console.error('Unlock prompt failed:', error)
    } finally {
      promptUnlockingPostId.value = null
    }
  }

  return {
    promptUnlockingPostId,
    handleUnlockPrompt,
  }
}
