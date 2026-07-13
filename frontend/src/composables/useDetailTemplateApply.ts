import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { getUnifiedApplyContext } from '@/api/gallery'
import { useTemplateApplyReplaceProtocol } from '@/composables/useTemplateApplyCloseProtocol'
import type {
  CloseTrigger,
  OpenTemplateApplyParams,
  OpenTemplateApplyResult,
  RequestCloseResult,
  TemplateApplySource,
} from '@/types/templateApply'

interface DetailApplyTarget {
  id: number
}

interface TemplateApplyStoreLike {
  requestClose: (trigger: CloseTrigger) => Promise<RequestCloseResult>
  openFromRawContext: (params: OpenTemplateApplyParams) => Promise<OpenTemplateApplyResult>
  confirmCloseAndCleanup: (trigger: CloseTrigger) => Promise<void>
}

interface UseDetailTemplateApplyOptions<TPost extends DetailApplyTarget> {
  currentPost: Ref<TPost | null>
  detailVisible: Ref<boolean>
  itemId: (post: TPost) => number | string
  source: TemplateApplySource | ((post: TPost) => TemplateApplySource)
  entryEntityId?: (post: TPost) => number | string | null
  templateApplyStore: TemplateApplyStoreLike
  t: (key: string) => string
  successMessageKey?: string
  errorMessageKey?: string
  ignoreNotFound?: boolean
  isApplyDisabled?: (post: TPost) => boolean
  getApplyDisabledMessage?: (post: TPost) => string
}

export function useDetailTemplateApply<TPost extends DetailApplyTarget>(
  options: UseDetailTemplateApplyOptions<TPost>
) {
  const applying = ref(false)
  const { openTemplateApplyWithReplaceConfirm } = useTemplateApplyReplaceProtocol(
    options.templateApplyStore
  )

  let applyRequestToken = 0
  let pendingApplyAbortController: AbortController | null = null
  let isUnmounted = false

  const cancelPendingApply = () => {
    applyRequestToken += 1
    pendingApplyAbortController?.abort()
    pendingApplyAbortController = null
    applying.value = false
  }

  const openTemplateWorkbench = async (
    rawContext: any,
    snapshot: {
      source: TemplateApplySource
      entryEntityId: number | string | null
    }
  ): Promise<boolean> => {
    const result = await openTemplateApplyWithReplaceConfirm({
      source: snapshot.source,
      entryEntityId: snapshot.entryEntityId,
      rawContext
    })

    if (result.status === 'opened') {
      options.detailVisible.value = false
      message.success(options.t(options.successMessageKey || 'template_apply.open_success'))
      return true
    }

    if (result.status === 'unsupported') {
      message.warning(options.t('template_apply.unknown_task_type'))
      return false
    }

    if (result.status === 'invalid') {
      message.error(result.message)
      return false
    }

    return false
  }

  const handleApply = async () => {
    const post = options.currentPost.value
    if (!post || applying.value) {
      return
    }
    if (options.isApplyDisabled?.(post)) {
      const disabledMessage = options.getApplyDisabledMessage?.(post)
        || options.t('template_apply.disabled.unsupported')
      message.warning(disabledMessage)
      return
    }

    const snapshot = {
      postId: post.id,
      source: typeof options.source === 'function' ? options.source(post) : options.source,
      entryEntityId: options.entryEntityId?.(post) ?? post.id,
      itemId: options.itemId(post),
    }

    const requestToken = ++applyRequestToken
    pendingApplyAbortController?.abort()
    const abortController = new AbortController()
    pendingApplyAbortController = abortController
    applying.value = true

    try {
      const rawContext = await getUnifiedApplyContext({
        source: snapshot.source,
        itemId: snapshot.itemId,
        signal: abortController.signal,
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

      await openTemplateWorkbench(rawContext, snapshot)
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

  watch(
    options.detailVisible,
    (visible, previousVisible) => {
      if (!visible && previousVisible) {
        cancelPendingApply()
      }
    },
    { flush: 'sync' }
  )

  return {
    applying,
    handleApply,
    cancelPendingApply,
  }
}
