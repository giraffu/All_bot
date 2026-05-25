import { confirmTemplateApplyClose } from '@/stores/templateApply'
import type {
  CloseTrigger,
  OpenTemplateApplyParams,
  OpenTemplateApplyResult,
  RequestCloseResult
} from '@/types/templateApply'

interface TemplateApplyCloseStoreLike {
  requestClose: (trigger: CloseTrigger) => Promise<RequestCloseResult>
  confirmCloseAndCleanup: (trigger: CloseTrigger) => Promise<void>
}

interface TemplateApplyReplaceStoreLike extends TemplateApplyCloseStoreLike {
  openFromRawContext: (params: OpenTemplateApplyParams) => Promise<OpenTemplateApplyResult>
}

export function useTemplateApplyCloseProtocol(store: TemplateApplyCloseStoreLike) {
  const attemptTemplateApplyClose = async (trigger: CloseTrigger): Promise<RequestCloseResult> => {
    const result = await store.requestClose(trigger)
    if (result.status === 'blocked') {
      return result
    }

    if (result.status === 'confirm_required') {
      const confirmed = await confirmTemplateApplyClose(result.confirmReason)
      if (!confirmed) {
        return result
      }
    }

    await store.confirmCloseAndCleanup(trigger)
    return result
  }

  return {
    attemptTemplateApplyClose
  }
}

export function useTemplateApplyReplaceProtocol(store: TemplateApplyReplaceStoreLike) {
  const openTemplateApplyWithReplaceConfirm = async (
    params: OpenTemplateApplyParams
  ): Promise<OpenTemplateApplyResult> => {
    const result = await store.openFromRawContext(params)
    if (result.status !== 'confirm_required') {
      return result
    }

    const confirmed = await confirmTemplateApplyClose(result.confirmReason)
    if (!confirmed) {
      return result
    }

    await store.confirmCloseAndCleanup('open_replace')
    return store.openFromRawContext(params)
  }

  return {
    openTemplateApplyWithReplaceConfirm
  }
}
