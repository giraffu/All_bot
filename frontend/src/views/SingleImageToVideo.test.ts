// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import SingleImageToVideo from './SingleImageToVideo.vue'

const mocks = vi.hoisted(() => ({
  route: {
    query: {
      type: 'ltx_video',
      title: '高级图生视频',
      ltx_extend_key: 'history/ltx-task-1/last_frame.png',
      ltx_extend_url: 'https://cdn/ltx-tail.png',
    } as Record<string, string>,
    meta: {},
  },
  uploadFile: vi.fn(),
  submitTask: vi.fn(),
  setSubmittedTaskId: vi.fn(),
  downloadResult: vi.fn(),
  isImageUrl: vi.fn(() => false),
  loadApplyContext: vi.fn(() => null),
  message: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
}))

vi.mock('ant-design-vue', () => ({
  message: mocks.message,
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({
    uploading: ref(false),
    progress: ref(0),
    uploadFile: mocks.uploadFile,
  }),
}))

vi.mock('@/composables/useTaskStream', () => ({
  useTaskStream: () => ({
    isSubmitting: ref(false),
    submitTask: mocks.submitTask,
  }),
}))

vi.mock('@/composables/useTaskResult', () => ({
  useTaskResult: () => ({
    currentTask: ref(null),
    setSubmittedTaskId: mocks.setSubmittedTaskId,
    isImageUrl: mocks.isImageUrl,
    downloadResult: mocks.downloadResult,
  }),
}))

vi.mock('@/composables/useGalleryApplyContext', () => ({
  useGalleryApplyContext: () => ({
    loadApplyContext: mocks.loadApplyContext,
  }),
}))

const mountView = () => mount(SingleImageToVideo, {
  global: {
    stubs: {
      GenerationWorkbenchShell: {
        props: ['title'],
        template: '<main><h1>{{ title }}</h1><slot name="left-top" /><slot name="left-content" /><slot name="left-footer" /><slot name="right-panel" /></main>',
      },
      GenerationUploadCard: {
        props: ['title', 'locked', 'lockedText'],
        template: '<section><h2>{{ title }}</h2><div v-if="locked">{{ lockedText }}</div><slot /></section>',
      },
      GenerationActionBar: true,
      TaskResultPreviewPanel: true,
      'a-select': { template: '<div><slot /></div>' },
      'a-select-option': { template: '<option><slot /></option>' },
      'a-radio-group': { template: '<div><slot /></div>' },
      'a-radio-button': { template: '<button><slot /></button>' },
      'a-button': { template: '<button><slot /></button>' },
      'a-slider': true,
      'a-input-number': true,
      'a-progress': true,
      'a-textarea': true,
    },
  },
})

describe('SingleImageToVideo LTX extension compatibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:preview'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('hides the LTX mode switch and locks the previous tail frame', async () => {
    const wrapper = mountView()
    await nextTick()

    expect(wrapper.text()).not.toContain('生成模式')
    expect(wrapper.text()).not.toContain('单首帧')
    expect(wrapper.text()).not.toContain('视频配音')
    expect(wrapper.text()).toContain('锁定起始帧')
    expect(wrapper.text()).toContain('已锁定为上一段尾帧')
    expect(wrapper.text()).toContain('可选终止帧')
    expect(mocks.message.success).toHaveBeenCalledWith('已载入历史尾帧')
  })
})
