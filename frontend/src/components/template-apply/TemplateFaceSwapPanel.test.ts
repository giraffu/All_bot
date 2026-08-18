// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateFaceSwapPanel from '@/components/template-apply/TemplateFaceSwapPanel.vue'
import type { TemplateApplyContext } from '@/types/templateApply'

const {
  sharedRefs,
  uploadFileMock,
  submitTaskMock,
  setSubmittedTaskIdMock,
  downloadResultMock,
  templateApplyStoreMock,
  messageWarningMock,
  messageErrorMock
} = vi.hoisted(() => ({
  sharedRefs: {
    hasPendingUploadsRef: undefined as any,
    uploadingSlotsRef: undefined as any,
    progressBySlotRef: undefined as any,
    isSubmittingRef: undefined as any,
    currentTaskRef: undefined as any
  },
  uploadFileMock: vi.fn(),
  submitTaskMock: vi.fn(),
  setSubmittedTaskIdMock: vi.fn(),
  downloadResultMock: vi.fn(),
  templateApplyStoreMock: {
    setPendingUploads: vi.fn(),
    setDirtyState: vi.fn(),
    registerPanelController: vi.fn(),
    closeAfterSubmission: vi.fn()
  },
  messageWarningMock: vi.fn(),
  messageErrorMock: vi.fn()
}))

vi.mock('@/composables/useTemplateApplyUpload', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  sharedRefs.hasPendingUploadsRef = ref(false)
  sharedRefs.uploadingSlotsRef = ref<Record<string, boolean>>({})
  sharedRefs.progressBySlotRef = ref<Record<string, number>>({})

  return {
    useTemplateApplyUpload: () => ({
      uploadFile: uploadFileMock,
      uploadingSlots: sharedRefs.uploadingSlotsRef,
      progressBySlot: sharedRefs.progressBySlotRef,
      hasPendingUploads: sharedRefs.hasPendingUploadsRef
    })
  }
})

vi.mock('@/composables/useTaskSubmission', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  sharedRefs.isSubmittingRef = ref(false)

  return {
    useTaskSubmission: () => ({
      isSubmitting: sharedRefs.isSubmittingRef,
      submitTask: submitTaskMock
    })
  }
})

vi.mock('@/composables/useTaskResult', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  sharedRefs.currentTaskRef = ref(null)

  return {
    useTaskResult: () => ({
      currentTask: sharedRefs.currentTaskRef,
      setSubmittedTaskId: setSubmittedTaskIdMock,
      downloadResult: downloadResultMock
    })
  }
})

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock
}))

vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<object>('ant-design-vue')
  return {
    ...actual,
    message: {
      warning: messageWarningMock,
      error: messageErrorMock,
      success: vi.fn()
    }
  }
})

vi.mock('@ant-design/icons-vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const stub = (name: string) =>
    defineComponent({
      name,
      template: `<span class="${name}" />`
    })

  return {
    CloseCircleOutlined: stub('close-circle-icon'),
    DownloadOutlined: stub('download-icon'),
    InboxOutlined: stub('inbox-icon'),
    SwapOutlined: stub('swap-icon')
  }
})

const UploadDraggerStub = defineComponent({
  name: 'AUploadDragger',
  props: {
    beforeUpload: {
      type: Function,
      required: true
    }
  },
  template: '<div class="upload-dragger-stub"><slot /></div>'
})

const ButtonStub = defineComponent({
  name: 'AButton',
  props: ['disabled', 'loading', 'type', 'size'],
  emits: ['click'],
  template: '<button class="a-button-stub" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
})

const ProgressStub = defineComponent({
  name: 'AProgress',
  props: ['percent', 'status', 'size'],
  template: '<div class="a-progress-stub">{{ percent }}</div>'
})

const buildContext = (overrides: Record<string, unknown> = {}): TemplateApplyContext => ({
  raw: {
    post_id: 1,
    source_post_id: 99,
    task_id: 'task-template',
    media_type: 'image',
    input_file: 'history/demo/template-target.png',
    input_file_url: 'https://example.com/template-target.png',
    task_type: 'face_swap'
  },
  source: 'gallery',
  entryEntityId: 1,
  rawEntityId: 1,
  rawTaskType: 'face_swap',
  taskType: 'face_swap',
  sourcePostId: 99,
  prompt: 'demo',
  negativePrompt: null,
  loraName: null,
  loraStrength: null,
  loraItems: [],
  inputFile: 'history/demo/template-target.png',
  inputFileUrl: 'https://example.com/template-target.png',
  width: 512,
  height: 512,
  duration: null,
  requestedDuration: null,
  billingResolution: null,
  ...overrides
})

const mountPanel = (contextOverrides: Record<string, unknown> = {}) =>
  mount(TemplateFaceSwapPanel, {
    props: {
      sessionId: 'session-1',
      context: buildContext(contextOverrides)
    },
    global: {
      plugins: [i18n],
      stubs: {
        'a-upload-dragger': UploadDraggerStub,
        'a-button': ButtonStub,
        'a-progress': ProgressStub,
        AUploadDragger: UploadDraggerStub,
        AButton: ButtonStub,
        AProgress: ProgressStub
      }
    }
  })

describe('TemplateFaceSwapPanel', () => {
  const createObjectURLMock = vi.fn(() => 'blob:face-preview')
  const revokeObjectURLMock = vi.fn()

  beforeEach(() => {
    uploadFileMock.mockReset()
    uploadFileMock.mockResolvedValue({
      uploadId: 'upload-1',
      objectKey: 'uploads/face.png'
    })

    sharedRefs.hasPendingUploadsRef.value = false
    sharedRefs.uploadingSlotsRef.value = {}
    sharedRefs.progressBySlotRef.value = {}

    submitTaskMock.mockReset()
    submitTaskMock.mockResolvedValue('task-123')
    sharedRefs.isSubmittingRef.value = false

    sharedRefs.currentTaskRef.value = null
    setSubmittedTaskIdMock.mockReset()
    downloadResultMock.mockReset()

    templateApplyStoreMock.setPendingUploads.mockReset()
    templateApplyStoreMock.setDirtyState.mockReset()
    templateApplyStoreMock.registerPanelController.mockReset()

    messageWarningMock.mockReset()
    messageErrorMock.mockReset()

    vi.stubGlobal('URL', {
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock
    })
    createObjectURLMock.mockClear()
    revokeObjectURLMock.mockClear()
  })

  it('initializes from template context and registers cleanup on mount', async () => {
    const wrapper = mountPanel()
    await nextTick()

    expect(wrapper.text()).toContain('已加载一键换脸模板')
    expect(wrapper.text()).not.toContain('目标图')
    expect(wrapper.findAllComponents(UploadDraggerStub)).toHaveLength(1)
    expect(setSubmittedTaskIdMock).toHaveBeenCalledWith(null)
    expect(templateApplyStoreMock.setDirtyState).toHaveBeenCalledWith(false)
    expect(templateApplyStoreMock.registerPanelController).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 'session-1',
        cleanup: expect.any(Function)
      })
    )
  })

  it('hides the locked target section for template apply', async () => {
    const wrapper = mountPanel({
      inputFileUrl: null
    })
    await nextTick()

    const uploaders = wrapper.findAllComponents(UploadDraggerStub)

    expect(uploaders).toHaveLength(1)
    expect(wrapper.text()).not.toContain('目标图')
    expect(messageWarningMock).not.toHaveBeenCalled()
    expect(uploadFileMock).not.toHaveBeenCalled()
  })

  it('submits the expected template payload after uploading the face image', async () => {
    const wrapper = mountPanel()
    await nextTick()

    const file = new File(['face'], 'face.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)

    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('开始换脸'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file, { slot: 'face_image' })
    expect(createObjectURLMock).toHaveBeenCalledWith(file)
    expect(submitTaskMock).toHaveBeenCalledWith(
      {
        task_type: 'face_swap',
        inputs: {
          face_image: 'uploads/face.png',
          target_image: 'history/demo/template-target.png'
        },
        priority: 0,
        is_template: true,
        source_post_id: 99
      },
      '快速换脸'
    )
    expect(setSubmittedTaskIdMock).toHaveBeenLastCalledWith('task-123')
  })

  it('propagates pending upload state and clears local state on unmount', async () => {
    const wrapper = mountPanel()
    await nextTick()

    sharedRefs.hasPendingUploadsRef.value = true
    await nextTick()

    expect(templateApplyStoreMock.setPendingUploads).toHaveBeenLastCalledWith(true)

    uploadFileMock.mockResolvedValueOnce({
      uploadId: 'upload-2',
      objectKey: 'uploads/cleanup-face.png'
    })

    const file = new File(['cleanup'], 'cleanup.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    wrapper.unmount()

    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:face-preview')
    expect(templateApplyStoreMock.setDirtyState).toHaveBeenCalledWith(false)
    expect(templateApplyStoreMock.setPendingUploads).toHaveBeenCalledWith(false)
    expect(setSubmittedTaskIdMock).toHaveBeenLastCalledWith(null)
    expect(templateApplyStoreMock.registerPanelController).toHaveBeenLastCalledWith(null)
  })
})
