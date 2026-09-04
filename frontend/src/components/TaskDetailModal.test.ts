// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskDetailModal from './TaskDetailModal.vue'

const routerPush = vi.fn()
const closeDetailModal = vi.fn()
const showDetailRecord = vi.fn()
let currentDetailRecord: any

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => (
      params?.count ? `${key}:${params.count}` : key
    ),
  }),
}))

vi.mock('@/composables/useViewport', () => ({
  useViewport: () => ({ isMobile: false }),
}))

vi.mock('@/stores/tasks', () => ({
  useTasksStore: () => ({
    detailModalVisible: true,
    currentDetailRecord,
    closeDetailModal,
    showDetailRecord,
  }),
}))

vi.mock('@/composables/useTaskFormat', () => ({
  useTaskFormat: () => ({
    formatDate: () => '2026-06-02',
    getTypeLabel: () => '图生视频 v2',
    getFileUrl: (value: string) => value,
    isVideoFile: () => true,
  }),
}))

vi.mock('@/composables/useTaskInteraction', () => ({
  useTaskInteraction: () => ({
    submittingTasks: {},
    submitToGallery: vi.fn(),
    handleFavorite: vi.fn(),
    handleDelete: vi.fn(),
    handleDownload: vi.fn(),
    handleSendToBot: vi.fn(),
  }),
}))

vi.mock('@/composables/usePostPromptCopy', () => ({
  usePostPromptCopy: () => ({
    copyPrompt: vi.fn(),
  }),
}))

vi.mock('@/api/gallery', () => ({
  stitchLtxHistoryChain: vi.fn(),
  stitchMiniMaxH3HistoryChain: vi.fn(),
  stitchWan22HistoryChain: vi.fn(),
}))

const mountModal = () => mount(TaskDetailModal, {
  global: {
    mocks: {
      $t: (key: string, params?: Record<string, unknown>) => (
        params?.count ? `${key}:${params.count}` : key
      ),
    },
    stubs: {
      'a-modal': {
        props: ['open'],
        template: '<div v-if="open"><slot /></div>',
      },
      'a-button': {
        props: ['disabled', 'loading'],
        emits: ['click'],
        template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
      },
      'a-tag': { template: '<span><slot /></span>' },
      PromptPreviewPanel: true,
    },
  },
})

describe('TaskDetailModal Wan22 editor links', () => {
  beforeEach(() => {
    routerPush.mockReset()
    closeDetailModal.mockReset()
    showDetailRecord.mockReset()
    currentDetailRecord = {
      id: 1,
      task_id: 'wan22-task-1',
      type: 'wan22_video_v2',
      prompt: 'segment prompt',
      input_file: 'bot-data/start.png',
      input_file_urls: ['https://cdn/start.png'],
      output_file: 'bot-data/result.mp4',
      output_file_url: 'https://cdn/result.mp4',
      extra_outputs: {
        last_frame: {
          path: 'tail.png',
          media_type: 'image',
          url: 'https://cdn/tail.png',
        },
      },
      result_meta: {
        wan22_segment_index: 1,
      },
      created_at: '2026-06-02T00:00:00Z',
      source: 'web',
      allow_contribute: false,
    }
  })

  it('routes Wan22 extension editing back to the lab workbench', async () => {
    const wrapper = mountModal()

    expect(wrapper.text()).toContain('original_inputs.title')

    await wrapper.findAll('button')
      .find(button => button.text().includes('扩展下一段'))
      ?.trigger('click')

    expect(routerPush).toHaveBeenCalledWith({
      name: 'CustomFeatures',
      query: {
        type: 'wan22_video_v2',
        wan22_mode: 'extend',
        wan22_task_id: 'wan22-task-1',
      },
    })
  })

  it('routes LTX extension editing with the last frame prefill key', async () => {
    currentDetailRecord = {
      ...currentDetailRecord,
      task_id: 'ltx-task-1',
      type: 'ltx_video',
      extra_outputs: {
        last_frame: {
          path: 'history/ltx-task-1/last_frame.png',
          media_type: 'image',
          url: 'https://cdn/ltx-tail.png',
        },
      },
      result_meta: {},
    }
    const wrapper = mountModal()

    await wrapper.findAll('button')
      .find(button => button.text().includes('扩展下一段'))
      ?.trigger('click')

    expect(routerPush).toHaveBeenCalledWith({
      name: 'CustomFeatures',
      query: {
        type: 'ltx_video',
        ltx_extend_task_id: 'ltx-task-1',
        ltx_extend_key: 'history/ltx-task-1/last_frame.png',
        ltx_extend_url: 'https://cdn/ltx-tail.png',
      },
    })
  })

  it('shows contribution actions for H3 image modes but not T2V', async () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    currentDetailRecord = {
      ...currentDetailRecord,
      type: 'minimax_h3_i2v',
      allow_contribute: true,
      is_public: false,
    }
    const supported = mountModal()
    expect(supported.text()).toContain('history.submit')

    currentDetailRecord = { ...currentDetailRecord, type: 'minimax_h3_t2v' }
    const unsupported = mountModal()
    expect(unsupported.text()).toContain('history.cannot_post')
  })

  it('routes H3 extension with only the server-owned parent task id', async () => {
    currentDetailRecord = {
      ...currentDetailRecord,
      task_id: 'h3-task-2',
      type: 'minimax_h3_ref2v',
      extra_outputs: {
        last_frame: {
          path: 'history/h3-task-2/last_frame.png',
          media_type: 'image',
          url: 'https://cdn/h3-tail.png',
        },
      },
      result_meta: {
        minimax_h3_prev_task_id: 'h3-task-1',
        minimax_h3_segment_index: 2,
      },
    }
    const wrapper = mountModal()
    await wrapper.findAll('button')
      .find(button => button.text().includes('lab.workbench.minimax_h3_extend_generation'))
      ?.trigger('click')

    expect(routerPush).toHaveBeenCalledWith({
      name: 'CustomFeatures',
      query: {
        type: 'minimax_h3_ref2v',
        minimax_h3_extend_task_id: 'h3-task-2',
      },
    })
  })

  it('requires a stored H3 tail frame before enabling extension', () => {
    currentDetailRecord = {
      ...currentDetailRecord,
      task_id: 'h3-task-without-tail',
      type: 'minimax_h3_ref2v',
      extra_outputs: {},
    }

    const wrapper = mountModal()
    const extendButton = wrapper.findAll('button')
      .find(button => button.text().includes('lab.workbench.minimax_h3_extend_generation'))

    expect(extendButton?.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('lab.workbench.minimax_h3_extend_missing_last_frame')
  })
})
