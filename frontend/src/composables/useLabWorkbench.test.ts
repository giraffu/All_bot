// @vitest-environment jsdom

import { describe, expect, it, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

import {
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
  useLabWorkbench,
} from './useLabWorkbench'

const mocks = vi.hoisted(() => ({
  route: {
    name: 'CustomFeatures',
    query: {} as Record<string, string>,
  },
  router: {
    push: vi.fn(),
    replace: vi.fn(),
  },
  uploadFile: vi.fn(),
  submitTask: vi.fn(),
  setSubmittedTaskId: vi.fn(),
  downloadResult: vi.fn(),
  isImageUrl: vi.fn(() => false),
  taskResultCurrentTask: { value: null as any },
  message: {
    warning: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(() => vi.fn()),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

vi.mock('vue-i18n', () => ({
  createI18n: () => ({
    global: {
      t: (key: string) => key,
    },
  }),
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('ant-design-vue', () => ({
  message: mocks.message,
  Modal: {
    confirm: vi.fn(),
  },
}))

vi.mock('@/composables/useGalleryApplyContext', () => ({
  useGalleryApplyContext: () => ({
    loadApplyContext: vi.fn(() => null),
    clearApplyContext: vi.fn(),
  }),
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({
    uploading: ref(false),
    progress: ref(0),
    uploadFile: mocks.uploadFile,
  }),
}))

vi.mock('@/composables/useTaskSubmission', () => ({
  useTaskSubmission: () => ({
    isSubmitting: ref(false),
    submitTask: mocks.submitTask,
  }),
}))

vi.mock('@/composables/useTaskResult', () => ({
  useTaskResult: () => ({
    currentTask: mocks.taskResultCurrentTask,
    setSubmittedTaskId: mocks.setSubmittedTaskId,
    isImageUrl: mocks.isImageUrl,
    downloadResult: mocks.downloadResult,
  }),
}))

vi.mock('@/stores/tasks', () => ({
  useTasksStore: () => ({
    showDetailRecord: vi.fn(),
    activeTasks: [],
    pendingPromptApplyTaskId: null,
    consumePromptTaskApply: vi.fn(),
  }),
}))

vi.mock('@/api/gallery', () => ({
  getWan22HistoryChain: vi.fn(),
  stitchLtxHistoryChain: vi.fn(),
  stitchMiniMaxH3HistoryChain: vi.fn(),
  stitchWan22HistoryChain: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

const createObjectURL = vi.fn(() => 'blob:preview')
const revokeObjectURL = vi.fn()

const createWorkbench = (type: string, query: Record<string, string> = {}) => {
  mocks.route.query = { type, ...query }
  return useLabWorkbench()
}

describe('useLabWorkbench SCAIL-2 upload limits', () => {
  it('limits SCAIL-2 motion videos to 40MB in the browser', () => {
    expect(SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES).toBe(40 * 1024 * 1024)
    expect(SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL).toBe('40MB')
  })
})

describe('useLabWorkbench LTX payloads', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.route.name = 'CustomFeatures'
    mocks.route.query = {}
    mocks.taskResultCurrentTask.value = null
    mocks.uploadFile.mockImplementation(async (file: File) => `uploads/${file.name}`)
    mocks.submitTask.mockResolvedValue('submitted-task-1')
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
  })

  it('submits advanced LTX single-start-frame tasks as i2v with last-frame extraction', async () => {
    const workbench = createWorkbench('ltx_video')
    workbench.uploadedReferences.value = [{
      key: 'input/start.png',
      preview: 'https://cdn/start.png',
      name: 'start.png',
    }]
    workbench.prompt.value = '  cinematic motion  '
    workbench.duration.value = '10'

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith({
      task_type: 'ltx_video',
      inputs: {
        images: ['input/start.png'],
        prompt: 'cinematic motion',
        resolution: '1280x704',
        duration: 10,
        ltx_mode: 'i2v',
        use_end_frame: false,
        extract_last_frame: true,
      },
      priority: 0,
      is_template: false,
    }, 'lab.cards.high_res_video_title')
    expect(mocks.setSubmittedTaskId).toHaveBeenCalledWith('submitted-task-1')
  })

  it('submits advanced LTX first-last-frame tasks as flf2v', async () => {
    const workbench = createWorkbench('ltx_video')
    workbench.uploadedReferences.value = [
      {
        key: 'input/start.png',
        preview: 'https://cdn/start.png',
        name: 'start.png',
      },
      {
        key: 'input/end.png',
        preview: 'https://cdn/end.png',
        name: 'end.png',
      },
    ]

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_video',
      inputs: expect.objectContaining({
        images: ['input/start.png', 'input/end.png'],
        ltx_mode: 'flf2v',
        use_end_frame: true,
        extract_last_frame: true,
      }),
    }), 'lab.cards.high_res_video_title')
  })

  it('loads LTX extension route tail frames as locked start frames', () => {
    const workbench = createWorkbench('ltx_video', {
      ltx_extend_task_id: 'ltx-task-1',
      ltx_extend_key: 'history/ltx-task-1/last_frame.png',
      ltx_extend_url: 'https://cdn/ltx-tail.png',
    })

    expect(workbench.currentMode.value.id).toBe('ltx_video')
    expect(workbench.uploadedReferences.value).toEqual([{
      key: 'history/ltx-task-1/last_frame.png',
      preview: 'https://cdn/ltx-tail.png',
      name: 'lab.workbench.ltx_extension_start_frame_name',
      locked: true,
      lockedLabel: 'lab.workbench.ltx_locked_start_frame',
    }])
    expect(workbench.uploadButtonLabel.value).toBe('lab.workbench.add_end_frame')
    expect(workbench.composerNotice.value).toBe('lab.workbench.ltx_extension_notice')
  })

  it('restores an H3 extension route and keeps its tail frame across I2V/FLF2V', async () => {
    const workbench = createWorkbench('minimax_h3_i2v', {
      minimax_h3_extend_task_id: 'h3-task-1',
      minimax_h3_extend_key: 'history/h3-task-1/last_frame.png',
      minimax_h3_extend_url: 'https://cdn/h3-tail.png',
    })

    expect(workbench.currentMode.value.id).toBe('minimax_h3')
    expect(workbench.h3IsExtension.value).toBe(true)
    expect(workbench.uploadedReferences.value[0]).toMatchObject({
      key: 'history/h3-task-1/last_frame.png',
      locked: true,
    })

    workbench.minimaxH3Mode.value = 'flf2v'
    await Promise.resolve()
    expect(workbench.uploadedReferences.value).toHaveLength(1)
    expect(workbench.uploadedReferences.value[0]?.locked).toBe(true)

    workbench.minimaxH3Mode.value = 'i2v'
    await Promise.resolve()
    expect(workbench.uploadedReferences.value[0]?.key)
      .toBe('history/h3-task-1/last_frame.png')
  })

  it('loads current LTX result tail frames as locked start frames', () => {
    mocks.taskResultCurrentTask.value = {
      id: 'ltx-task-1',
      type: 'ltx_video',
      status: 'success',
      extraOutputs: {
        last_frame: {
          path: 'history/ltx-task-1/last_frame.png',
          url: 'https://cdn/ltx-tail.png',
        },
      },
    }
    const workbench = createWorkbench('ltx_video')

    workbench.openLtxCurrentTaskEditor()

    expect(workbench.uploadedReferences.value[0]).toMatchObject({
      key: 'history/ltx-task-1/last_frame.png',
      preview: 'https://cdn/ltx-tail.png',
      locked: true,
      lockedLabel: 'lab.workbench.ltx_locked_start_frame',
    })
    expect(mocks.message.success).toHaveBeenCalledWith('lab.workbench.ltx_extension_loaded')
  })

  it('submits locked LTX extension frames as i2v when no end frame is added', async () => {
    const workbench = createWorkbench('ltx_video', {
      ltx_extend_key: 'history/ltx-task-1/last_frame.png',
      ltx_extend_url: 'https://cdn/ltx-tail.png',
    })
    workbench.prompt.value = 'continue the motion'

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith({
      task_type: 'ltx_video',
      inputs: {
        images: ['history/ltx-task-1/last_frame.png'],
        prompt: 'continue the motion',
        resolution: '1280x704',
        duration: 5,
        ltx_mode: 'i2v',
        use_end_frame: false,
        extract_last_frame: true,
      },
      priority: 0,
      is_template: false,
    }, 'lab.cards.high_res_video_title')
  })

  it('submits LTX extension chain metadata when the previous task id is known', async () => {
    const workbench = createWorkbench('ltx_video', {
      ltx_extend_task_id: 'ltx-task-1',
      ltx_extend_key: 'history/ltx-task-1/last_frame.png',
      ltx_extend_url: 'https://cdn/ltx-tail.png',
    })
    workbench.prompt.value = 'continue the next segment'

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_video',
      inputs: expect.objectContaining({
        images: ['history/ltx-task-1/last_frame.png'],
        ltx_mode: 'i2v',
        ltx_prev_task_id: 'ltx-task-1',
        ltx_chain_task_ids: ['ltx-task-1'],
      }),
    }), 'lab.cards.high_res_video_title')
  })

  it('extends current LTX result with inherited chain metadata', async () => {
    mocks.taskResultCurrentTask.value = {
      id: 'ltx-task-2',
      type: 'ltx_video',
      status: 'success',
      extraOutputs: {
        last_frame: {
          path: 'history/ltx-task-2/last_frame.png',
          url: 'https://cdn/ltx-tail-2.png',
        },
      },
      resultMeta: {
        ltx_prev_task_id: 'ltx-task-1',
        ltx_chain_task_ids: ['ltx-task-1'],
      },
    }
    const workbench = createWorkbench('ltx_video')
    workbench.openLtxCurrentTaskEditor()
    workbench.prompt.value = 'continue segment three'

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_video',
      inputs: expect.objectContaining({
        images: ['history/ltx-task-2/last_frame.png'],
        ltx_prev_task_id: 'ltx-task-2',
        ltx_chain_task_ids: ['ltx-task-1', 'ltx-task-2'],
      }),
    }), 'lab.cards.high_res_video_title')
  })

  it('submits locked LTX extension frames as flf2v when an optional end frame is added', async () => {
    const workbench = createWorkbench('ltx_video', {
      ltx_extend_key: 'history/ltx-task-1/last_frame.png',
      ltx_extend_url: 'https://cdn/ltx-tail.png',
    })
    workbench.uploadedReferences.value.push({
      key: 'input/new-end.png',
      preview: 'https://cdn/new-end.png',
      name: 'new-end.png',
    })

    await workbench.handleSubmit()

    expect(mocks.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_video',
      inputs: expect.objectContaining({
        images: ['history/ltx-task-1/last_frame.png', 'input/new-end.png'],
        ltx_mode: 'flf2v',
        use_end_frame: true,
        extract_last_frame: true,
      }),
    }), 'lab.cards.high_res_video_title')
  })
})
