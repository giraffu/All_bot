// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateVideoSwapPanel from '@/components/template-apply/TemplateVideoSwapPanel.vue'
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
      isVideoUrl: vi.fn(() => true),
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
    VideoCameraOutlined: stub('video-camera-icon')
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

const RadioGroupStub = defineComponent({
  name: 'ARadioGroup',
  props: ['value'],
  emits: ['update:value'],
  template: '<div class="a-radio-group-stub"><slot /></div>'
})

const RadioButtonStub = defineComponent({
  name: 'ARadioButton',
  props: ['value', 'disabled'],
  template: '<button class="a-radio-button-stub"><slot /></button>'
})

const buildContext = (overrides: Record<string, unknown> = {}): TemplateApplyContext => ({
  raw: {
    post_id: 1,
    source_post_id: 55,
    task_id: 'task-template-video',
    media_type: 'video',
    input_file: 'history/demo/template-target.mp4',
    input_file_url: 'https://example.com/template-target.mp4',
    task_type: 'face_video',
    width: 640,
    height: 800,
    billing_resolution: '720p'
  },
  source: 'gallery',
  entryEntityId: 1,
  rawEntityId: 1,
  rawTaskType: 'face_video',
  taskType: 'face_video',
  sourcePostId: 55,
  prompt: null,
  negativePrompt: null,
  loraName: null,
  loraStrength: null,
  loraItems: [],
  inputFile: 'history/demo/template-target.mp4',
  inputFileUrl: 'https://example.com/template-target.mp4',
  width: 640,
  height: 800,
  duration: 5,
  requestedDuration: null,
  billingResolution: '720p',
  ...overrides
})

const mountPanel = (contextOverrides: Record<string, unknown> = {}) =>
  mount(TemplateVideoSwapPanel, {
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
        'a-radio-group': RadioGroupStub,
        'a-radio-button': RadioButtonStub,
        AUploadDragger: UploadDraggerStub,
        AButton: ButtonStub,
        AProgress: ProgressStub,
        ARadioGroup: RadioGroupStub,
        ARadioButton: RadioButtonStub
      }
    }
  })

describe('TemplateVideoSwapPanel', () => {
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
    submitTaskMock.mockResolvedValue('task-456')
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

  it('prefers billing tier semantics over raw portrait width for face_video payloads', async () => {
    const wrapper = mountPanel()
    await nextTick()

    expect(wrapper.findAllComponents(UploadDraggerStub)).toHaveLength(1)
    expect(wrapper.html()).not.toContain('https://example.com/template-target.mp4')

    const file = new File(['face'], 'face.png', { type: 'image/png' })
    const uploaders = wrapper.findAllComponents(UploadDraggerStub)
    await uploaders[0]!.props('beforeUpload')(file)
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
    expect(submitTaskMock).toHaveBeenCalledWith(
      {
        task_type: 'face_video',
        inputs: {
          face_image: 'uploads/face.png',
          target_video: 'history/demo/template-target.mp4',
          resolution: 720
        },
        priority: 0,
        is_template: true,
        source_post_id: 55
      },
      '视频换脸'
    )
    expect(setSubmittedTaskIdMock).toHaveBeenLastCalledWith('task-456')
  })
})
