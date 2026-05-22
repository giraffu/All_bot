import { onBeforeUnmount, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api'
import { confirmTemplateApplyClose } from '@/stores/templateApply'
import type { TemplateApplySource } from '@/types/templateApply'
import {
  buildLegacyTemplateRoute,
  resolveTemplateApplyEntry
} from '@/utils/templateApplyEntry'

interface DetailApplyTarget {
  id: number
}

interface TemplateApplyStoreLike {
  openFromRawContext: (params: {
    source: TemplateApplySource
    entryEntityId: number | string | null
    rawContext: any
  }) => Promise<any>
  confirmCloseAndCleanup: (trigger: 'open_replace') => Promise<void>
}

interface UseDetailTemplateApplyOptions<TPost extends DetailApplyTarget> {
  currentPost: Ref<TPost | null>
  detailVisible: Ref<boolean>
  endpoint: (post: TPost) => string
  source: TemplateApplySource | ((post: TPost) => TemplateApplySource)
  entryEntityId?: (post: TPost) => number | string | null
  templateApplyStore: TemplateApplyStoreLike
  saveApplyContext: (rawContext: any) => void
  t: (key: string) => string
  successMessageKey?: string
  errorMessageKey?: string
  ignoreNotFound?: boolean
}

export function useDetailTemplateApply<TPost extends DetailApplyTarget>(
  options: UseDetailTemplateApplyOptions<TPost>
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
    source: TemplateApplySource
    entryEntityId: number | string | null
  }) => {
    const resolvedEntry = resolveTemplateApplyEntry({
      rawContext: params.rawContext,
      source: params.source,
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
    snapshot: {
      source: TemplateApplySource
      entryEntityId: number | string | null
    }
  ): Promise<boolean> => {
    const result = await options.templateApplyStore.openFromRawContext({
      source: snapshot.source,
      entryEntityId: snapshot.entryEntityId,
      rawContext
    })

    if (result.status === 'opened') {
      options.detailVisible.value = false
      message.success(options.t(options.successMessageKey || 'template_apply.open_success'))
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
        source: snapshot.source,
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
    const post = options.currentPost.value
    if (!post || applying.value) {
      return
    }

    const snapshot = {
      postId: post.id,
      source: typeof options.source === 'function' ? options.source(post) : options.source,
      entryEntityId: options.entryEntityId?.(post) ?? post.id,
      endpoint: options.endpoint(post)
    }

    const requestToken = ++applyRequestToken
    pendingApplyAbortController?.abort()
    const abortController = new AbortController()
    pendingApplyAbortController = abortController
    applying.value = true

    try {
      const res = await api.get(snapshot.endpoint, {
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
      if (options.ignoreNotFound && error?.response?.status === 404) {
        return
      }
      console.error(error)
      message.error(options.t(options.errorMessageKey || 'my_notes.template_load_failed'))
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
