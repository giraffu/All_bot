import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { modalConfirmMock } = vi.hoisted(() => ({
  modalConfirmMock: vi.fn()
}))

vi.mock('ant-design-vue', () => ({
  Modal: {
    confirm: modalConfirmMock
  }
}))

import { useTemplateApplyStore } from '@/stores/templateApply'
import { useTemplateApplyUploadStore } from '@/stores/templateApplyUpload'

describe('templateApply store', () => {
  beforeEach(() => {
    modalConfirmMock.mockReset()
    setActivePinia(createPinia())
  })

  it('opens supported tasks in workbench mode', async () => {
    const store = useTemplateApplyStore()

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        source_post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png',
        input_file_url: 'https://example.com/demo.png',
        prompt: 'demo prompt'
      }
    })

    expect(result.status).toBe('opened')
    expect(store.visible).toBe(true)
    expect(store.taskType).toBe('face_swap')
    expect(store.panelKind).toBe('faceSwap')
    expect(store.featureTitleKey).toBe('lab.cards.fast_face_swap_title')
  })

  it('opens i2i_pro in the image prompt workbench', async () => {
    const store = useTemplateApplyStore()

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 8,
      rawContext: {
        post_id: 8,
        source_post_id: 8,
        task_type: 'i2i_pro',
        input_file: 'history/demo/original.png',
        prompt: 'fantasy portrait'
      }
    })

    expect(result.status).toBe('opened')
    expect(store.taskType).toBe('i2i_pro')
    expect(store.panelKind).toBe('imagePrompt')
    expect(store.featureTitleKey).toBe('lab.cards.i2i_pro_title')
  })

  it('opens historical free edit in the v3 image prompt workbench', async () => {
    const store = useTemplateApplyStore()

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 18,
      rawContext: {
        post_id: 18,
        source_post_id: 18,
        task_type: 'pornmaster_flux2_single_edit',
        prompt: 'clean up the background'
      }
    })

    expect(result.status).toBe('opened')
    expect(store.taskType).toBe('pornmaster_flux2_edit_bf16')
    expect(store.panelKind).toBe('imagePrompt')
    expect(store.featureTitleKey).toBe('lab.cards.custom_edit_v3_title')
  })

  it('opens wan22_video_v2 in the image-to-video workbench', async () => {
    const store = useTemplateApplyStore()

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 12,
      rawContext: {
        post_id: 12,
        source_post_id: 12,
        task_type: 'wan22_video_v2',
        prompt: 'cinematic v2 motion',
        negative_prompt: 'low quality blur',
        billing_resolution: 'standard',
        requested_duration: 5
      }
    })

    expect(result.status).toBe('opened')
    expect(store.taskType).toBe('wan22_video_v2')
    expect(store.panelKind).toBe('imageToVideo')
    expect(store.featureTitleKey).toBe('lab.cards.wan22_video_v2_title')
    expect(store.context?.negativePrompt).toBe('low quality blur')
  })

  it('returns unsupported for unknown tasks', async () => {
    const store = useTemplateApplyStore()

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'unknown_task_type'
      }
    })

    expect(result).toMatchObject({
      status: 'unsupported',
      rawTaskType: 'unknown_task_type'
    })
    expect(store.visible).toBe(false)
  })

  it('requires confirmation when replacing a dirty visible session', async () => {
    const store = useTemplateApplyStore()

    await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'face_video',
        input_file: 'history/demo/original.mp4',
        input_file_url: 'https://example.com/demo.mp4'
      }
    })
    store.setDirtyState(true)

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 11,
      rawContext: {
        post_id: 11,
        task_type: 'custom_video',
        prompt: 'replace me'
      }
    })

    expect(result).toMatchObject({
      status: 'confirm_required',
      trigger: 'open_replace',
      confirmReason: 'dirty'
    })
    expect(store.taskType).toBe('scail2_face_swap_v2')
  })

  it('replaces a clean visible session immediately', async () => {
    const store = useTemplateApplyStore()

    const first = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })

    if (first.status !== 'opened') {
      throw new Error('Expected initial session to open')
    }

    const result = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 11,
      rawContext: {
        post_id: 11,
        task_type: 'custom_video',
        prompt: 'replace me'
      }
    })

    expect(result.status).toBe('opened')
    expect(store.taskType).toBe('custom_video')
    expect(store.panelKind).toBe('imageToVideo')
    expect(store.session?.entryEntityId).toBe(11)
  })

  it('does not let stale cleanup close a newer session', async () => {
    const store = useTemplateApplyStore()

    const first = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })
    const firstSessionId = first.status === 'opened' ? first.sessionId : ''

    await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 11,
      rawContext: {
        post_id: 11,
        task_type: 'custom_video',
        prompt: 'new session'
      }
    })

    store.forceCloseAfterCleanup(firstSessionId)

    expect(store.visible).toBe(true)
    expect(store.taskType).toBe('custom_video')
  })

  it('aborts uploads and runs panel cleanup when closing', async () => {
    const store = useTemplateApplyStore()
    const uploadStore = useTemplateApplyUploadStore()
    const cleanup = vi.fn().mockResolvedValue(undefined)
    const abortSpy = vi.spyOn(uploadStore, 'abortBySession')

    const opened = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })

    if (opened.status !== 'opened') {
      throw new Error('Expected session to open')
    }

    store.registerPanelController({
      sessionId: opened.sessionId,
      cleanup
    })

    await store.confirmCloseAndCleanup('user_close')

    expect(abortSpy).toHaveBeenCalledWith(opened.sessionId)
    expect(cleanup).toHaveBeenCalledTimes(1)
    expect(store.visible).toBe(false)
    expect(store.status).toBe('idle')
  })

  it('closes only the template session that submitted the task', async () => {
    const store = useTemplateApplyStore()
    const opened = await store.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })

    if (opened.status !== 'opened') {
      throw new Error('Expected session to open')
    }

    await store.closeAfterSubmission('stale-session')
    expect(store.visible).toBe(true)

    await store.closeAfterSubmission(opened.sessionId)
    expect(store.visible).toBe(false)
    expect(store.status).toBe('idle')
  })
})
