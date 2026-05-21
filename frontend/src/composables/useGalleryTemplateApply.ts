import { onBeforeUnmount, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api'
import { confirmTemplateApplyClose } from '@/stores/templateApply'
import {
  buildLegacyTemplateRoute,
  resolveTemplateApplyEntry
} from '@/utils/templateApplyEntry'

interface GalleryApplyPost {
  id: number
}

interface TemplateApplyStoreLike {
  openFromRawContext: (params: {
    source: 'gallery'
    entryEntityId: number | string | null
    rawContext: any
  }) => Promise<any>
  confirmCloseAndCleanup: (trigger: 'open_replace') => Promise<void>
}

interface UseGalleryTemplateApplyOptions<TPost extends GalleryApplyPost> {
  currentPost: Ref<TPost | null>
  detailVisible: Ref<boolean>
  templateApplyStore: TemplateApplyStoreLike
  saveApplyContext: (rawContext: any) => void
  t: (key: string) => string
}

export function useGalleryTemplateApply<TPost extends GalleryApplyPost>(
  options: UseGalleryTemplateApplyOptions<TPost>
) {
  const router = useRouter()
  const applying = ref(false)

  let applyRequestToken = 0
  let pendingApplyAbortController: AbortController | null = null
  let isUnmounted = false

  const cancelPendingApply = () => {
    applyRequestToken += 1
    pendingApplyAbortController?.abort()
    pendingApplyAbortController = null
    applying.value = false
  }

  const handleLegacyFallback = async (params: {
    rawContext: any
    entryEntityId: number | string | null
  }) => {
    const resolvedEntry = resolveTemplateApplyEntry({
      rawContext: params.rawContext,
      source: 'gallery',
      entryEntityId: params.entryEntityId,
      preferredMode: 'legacy'
    })

    if (resolvedEntry.status === 'invalid') {
      message.error(options.t('template_apply.invalid_context'))
      return false
    }

    if (resolvedEntry.status === 'unknown_task_type') {
      message.warning(options.t('template_apply.unknown_task_type'))
      return false
    }

    options.saveApplyContext(params.rawContext)
    options.detailVisible.value = false
    message.success(options.t('template_apply.legacy_loaded'))
    await router.push(buildLegacyTemplateRoute(resolvedEntry, options.t))
    return true
  }

  const openTemplateWorkbench = async (
    rawContext: any,
    snapshot: { entryEntityId: number | string | null }
  ): Promise<boolean> => {
    const result = await options.templateApplyStore.openFromRawContext({
      source: 'gallery',
      entryEntityId: snapshot.entryEntityId,
      rawContext
    })

    if (result.status === 'opened') {
      options.detailVisible.value = false
      message.success(options.t('template_apply.open_success'))
      return true
    }

    if (result.status === 'legacy_fallback') {
      if (result.fallbackKind === 'legacy_supported' && result.context && result.meta) {
        options.saveApplyContext(rawContext)
        options.detailVisible.value = false
        message.success(options.t('template_apply.legacy_loaded'))
        await router.push(buildLegacyTemplateRoute({
          status: 'legacy_supported',
          context: result.context,
          meta: result.meta
        }, options.t))
        return true
      }

      return handleLegacyFallback({
        rawContext,
        entryEntityId: snapshot.entryEntityId
      })
    }

    if (result.status === 'invalid') {
      message.error(result.message)
      return false
    }

    if (result.status === 'confirm_required') {
      const confirmed = await confirmTemplateApplyClose(result.confirmReason)
      if (!confirmed) {
        return false
      }
      await options.templateApplyStore.confirmCloseAndCleanup('open_replace')
      return openTemplateWorkbench(rawContext, snapshot)
    }

    return false
  }

  const handleApply = async () => {
    if (!options.currentPost.value || applying.value) return

    const snapshot = {
      postId: options.currentPost.value.id,
      entryEntityId: options.currentPost.value.id
    }

    const requestToken = ++applyRequestToken
    pendingApplyAbortController?.abort()
    const abortController = new AbortController()
    pendingApplyAbortController = abortController
    applying.value = true

    try {
      const res = await api.get(`/gallery/posts/${snapshot.postId}/apply-context`, {
        signal: abortController.signal
      })

      if (
        applyRequestToken !== requestToken
        || pendingApplyAbortController !== abortController
        || isUnmounted
        || !options.detailVisible.value
        || options.currentPost.value?.id !== snapshot.postId
      ) {
        return
      }

      await openTemplateWorkbench(res.data, snapshot)
    } catch (error: any) {
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        return
      }
      console.error(error)
      message.error(options.t('my_notes.template_load_failed'))
    } finally {
      if (pendingApplyAbortController === abortController) {
        pendingApplyAbortController = null
      }
      if (applyRequestToken === requestToken) {
        applying.value = false
      }
    }
  }

  onBeforeUnmount(() => {
    isUnmounted = true
    cancelPendingApply()
  })

  return {
    applying,
    handleApply,
    cancelPendingApply,
  }
}
