import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/api'
import type { TemplateApplySource } from '@/types/templateApply'
import {
  buildLegacyTemplateRoute,
  resolveTemplateApplyEntry
} from '@/utils/templateApplyEntry'

interface LegacyApplyTarget {
  id: number
}

interface UseLegacyTemplateApplyOptions<TPost extends LegacyApplyTarget> {
  currentPost: Ref<TPost | null>
  closeDetail: () => void
  saveApplyContext: (rawContext: any) => void
  t: (key: string) => string
}

interface ApplyFromCurrentPostOptions<TPost extends LegacyApplyTarget> {
  endpoint: (post: TPost) => string
  source: TemplateApplySource
  entryEntityId?: (post: TPost) => number | string | null
  successMessageKey?: string
  errorMessageKey?: string
  ignoreNotFound?: boolean
}

export function useLegacyTemplateApply<TPost extends LegacyApplyTarget>(
  options: UseLegacyTemplateApplyOptions<TPost>
) {
  const router = useRouter()
  const applying = ref(false)

  const applyFromCurrentPost = async (
    applyOptions: ApplyFromCurrentPostOptions<TPost>
  ) => {
    const post = options.currentPost.value
    if (!post || applying.value) return

    applying.value = true
    try {
      const res = await api.get(applyOptions.endpoint(post))
      const rawContext = res.data
      const resolvedEntry = resolveTemplateApplyEntry({
        rawContext,
        source: applyOptions.source,
        entryEntityId: applyOptions.entryEntityId?.(post) ?? post.id,
        preferredMode: 'legacy'
      })

      if (resolvedEntry.status === 'invalid') {
        message.error(options.t(applyOptions.errorMessageKey || 'my_notes.template_load_failed'))
        return
      }

      if (resolvedEntry.status === 'unknown_task_type') {
        message.warning(options.t('template_apply.unknown_task_type'))
        return
      }

      options.closeDetail()
      options.saveApplyContext(rawContext)
      message.success(options.t(applyOptions.successMessageKey || 'my_notes.template_loaded_with_upload_hint'))
      void router.push(buildLegacyTemplateRoute(resolvedEntry, options.t))
    } catch (error: any) {
      if (applyOptions.ignoreNotFound && error.response?.status === 404) {
        return
      }
      console.error(error)
      message.error(options.t(applyOptions.errorMessageKey || 'my_notes.template_load_failed'))
    } finally {
      applying.value = false
    }
  }

  return {
    applying,
    applyFromCurrentPost
  }
}
