import { defineStore } from 'pinia'
import { Modal } from 'ant-design-vue'
import { ref } from 'vue'
import i18n from '@/i18n'
import { useTemplateApplyUploadStore } from '@/stores/templateApplyUpload'
import type {
  CloseConfirmReason,
  CloseTrigger,
  OpenTemplateApplyParams,
  OpenTemplateApplyResult,
  RequestCloseResult,
  TemplateApplyContext,
  TemplateApplyPanelController,
  TemplateApplyPanelKind,
  TemplateApplySessionMeta,
  TemplateApplyTaskType
} from '@/types/templateApply'
import { resolveTemplateApplyEntry } from '@/utils/templateApplyEntry'

const createSessionId = () =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `template_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

const t = (key: string) => i18n.global.t(key)

const confirmReasonText: Record<CloseConfirmReason, string> = {
  dirty: 'template_apply.close.dirty',
  uploading: 'template_apply.close.uploading',
  dirty_and_uploading: 'template_apply.close.dirty_and_uploading'
}

export const confirmTemplateApplyClose = (reason: CloseConfirmReason): Promise<boolean> =>
  new Promise(resolve => {
    Modal.confirm({
      title: t('template_apply.close.title'),
      content: t(confirmReasonText[reason]),
      okText: t('template_apply.close.confirm'),
      cancelText: t('template_apply.close.cancel'),
      onOk: () => resolve(true),
      onCancel: () => resolve(false)
    })
  })

export const useTemplateApplyStore = defineStore('templateApply', () => {
  const visible = ref(false)
  const loading = ref(false)
  const status = ref<'idle' | 'opening' | 'visible' | 'closing'>('idle')
  const session = ref<TemplateApplySessionMeta | null>(null)
  const taskType = ref<TemplateApplyTaskType | null>(null)
  const panelKind = ref<TemplateApplyPanelKind | null>(null)
  const context = ref<TemplateApplyContext | null>(null)
  const featureTitleKey = ref<string | null>(null)
  const dirty = ref(false)
  const hasPendingUploads = ref(false)
  const panelController = ref<TemplateApplyPanelController | null>(null)

  const reset = () => {
    visible.value = false
    loading.value = false
    status.value = 'idle'
    session.value = null
    taskType.value = null
    panelKind.value = null
    context.value = null
    featureTitleKey.value = null
    dirty.value = false
    hasPendingUploads.value = false
    panelController.value = null
  }

  const setDirtyState = (isDirty: boolean) => {
    dirty.value = isDirty
  }

  const setPendingUploads = (pending: boolean) => {
    hasPendingUploads.value = pending
  }

  const registerPanelController = (controller: TemplateApplyPanelController | null) => {
    if (!controller) {
      panelController.value = null
      return
    }

    if (session.value?.sessionId !== controller.sessionId) {
      return
    }

    panelController.value = controller
  }

  const isSessionActive = (sessionId: string) =>
    !!sessionId
    && visible.value
    && status.value !== 'closing'
    && session.value?.sessionId === sessionId

  const requestClose = async (trigger: CloseTrigger): Promise<RequestCloseResult> => {
    if (!visible.value) {
      return { status: 'close_now' }
    }

    if (status.value === 'opening') {
      return { status: 'blocked', reason: 'opening' }
    }

    if (status.value === 'closing') {
      return { status: 'blocked', reason: 'closing' }
    }

    let confirmReason: CloseConfirmReason | null = null

    if (dirty.value && hasPendingUploads.value) {
      confirmReason = 'dirty_and_uploading'
    } else if (hasPendingUploads.value) {
      confirmReason = 'uploading'
    } else if (dirty.value) {
      confirmReason = 'dirty'
    }

    if (confirmReason) {
      return {
        status: 'confirm_required',
        trigger,
        confirmReason
      }
    }

    return { status: 'close_now' }
  }

  const forceCloseAfterCleanup = (sessionId: string) => {
    if (session.value?.sessionId !== sessionId) {
      return
    }

    reset()
  }

  const confirmCloseAndCleanup = async (trigger: CloseTrigger) => {
    if (!visible.value || !session.value) {
      reset()
      return
    }

    if (status.value === 'closing') {
      return
    }

    const uploadStore = useTemplateApplyUploadStore()
    const currentSessionId = session.value.sessionId
    status.value = 'closing'

    try {
      uploadStore.abortBySession(currentSessionId)
      await panelController.value?.cleanup?.()
    } catch (error) {
      console.error(`Template apply cleanup failed (${trigger})`, error)
    } finally {
      forceCloseAfterCleanup(currentSessionId)
    }
  }

  const openFromRawContext = async (
    params: OpenTemplateApplyParams
  ): Promise<OpenTemplateApplyResult> => {
    if (status.value === 'opening') {
      return { status: 'blocked', reason: 'opening' }
    }

    if (status.value === 'closing') {
      return { status: 'blocked', reason: 'closing' }
    }

    if (visible.value) {
      const closeResult = await requestClose('open_replace')
      if (closeResult.status === 'close_now') {
        await confirmCloseAndCleanup('open_replace')
      } else if (closeResult.status === 'confirm_required') {
        return {
          status: 'confirm_required',
          trigger: 'open_replace',
          confirmReason: closeResult.confirmReason
        }
      } else {
        return closeResult
      }
    }

    status.value = 'opening'
    loading.value = true

    try {
      const resolvedEntry = resolveTemplateApplyEntry({
        rawContext: params.rawContext,
        source: params.source,
        entryEntityId: params.entryEntityId,
        preferredMode: params.preferredMode
      })

      if (resolvedEntry.status === 'invalid') {
        reset()
        return {
          status: 'invalid',
          message: t('template_apply.invalid_context')
        }
      }

      if (resolvedEntry.status === 'unknown_task_type') {
        reset()
        return {
          status: 'legacy_fallback',
          fallbackKind: 'unknown_task_type',
          rawTaskType: resolvedEntry.context.rawTaskType,
          context: resolvedEntry.context,
          meta: null
        }
      }

      if (resolvedEntry.status === 'legacy_supported') {
        reset()
        return {
          status: 'legacy_fallback',
          fallbackKind: 'legacy_supported',
          rawTaskType: resolvedEntry.context.rawTaskType,
          context: resolvedEntry.context,
          meta: resolvedEntry.meta
        }
      }

      if (!resolvedEntry.context.taskType || !resolvedEntry.meta.panelKind) {
        reset()
        return {
          status: 'legacy_fallback',
          fallbackKind: 'legacy_supported',
          rawTaskType: resolvedEntry.context.rawTaskType,
          context: resolvedEntry.context,
          meta: resolvedEntry.meta
        }
      }

      const nextSessionId = createSessionId()

      session.value = {
        sessionId: nextSessionId,
        source: params.source,
        entryEntityId: params.entryEntityId,
        openedAt: Date.now()
      }
      visible.value = true
      taskType.value = resolvedEntry.context.taskType
      panelKind.value = resolvedEntry.meta.panelKind
      context.value = resolvedEntry.context
      featureTitleKey.value = resolvedEntry.meta.legacyTitleKey
      dirty.value = false
      hasPendingUploads.value = false
      panelController.value = null
      status.value = 'visible'
      loading.value = false

      return {
        status: 'opened',
        sessionId: nextSessionId
      }
    } catch (error) {
      console.error('Failed to open template apply workbench', error)
      reset()
      return {
        status: 'invalid',
        message: t('template_apply.open_failed')
      }
    }
  }

  return {
    visible,
    loading,
    status,
    session,
    taskType,
    panelKind,
    context,
    featureTitleKey,
    dirty,
    hasPendingUploads,
    panelController,
    openFromRawContext,
    setDirtyState,
    setPendingUploads,
    registerPanelController,
    isSessionActive,
    requestClose,
    confirmCloseAndCleanup,
    forceCloseAfterCleanup,
    reset
  }
})
