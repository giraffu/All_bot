// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateScail2VideoPanel from '@/components/template-apply/TemplateScail2VideoPanel.vue'
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
    registerPanelController: vi.fn()
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

vi.mock('@/composables/useTaskStream', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  sharedRefs.isSubmittingRef = ref(false)

  return {
    useTaskStream: () => ({
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
      isImageUrl: vi.fn(() => false),
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
    InboxOutlined: stub('inbox-icon'),
    VideoCameraOutlined: stub('video-camera-icon')
  }
})

vi.mock('@/components/template-apply/TemplateApplyResultSection.vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  return {
    default: defineComponent({
      name: 'TemplateApplyResultSectionStub',
      template: '<section class="result-section-stub" />'
    })
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

const TextareaStub = defineComponent({
  name: 'ATextarea',
  props: ['value', 'rows', 'placeholder'],
  emits: ['update:value'],
  template: '<textarea class="a-textarea-stub" :value="value" />'
})

const RadioGroupStub = defineComponent({
  name: 'ARadioGroup',
  props: ['value'],
  emits: ['update:value'],
  template: '<div class="a-radio-group-stub"><slot /></div>'
})

const RadioButtonStub = defineComponent({
  name: 'ARadioButton',
  props: ['value'],
  template: '<button class="a-radio-button-stub"><slot /></button>'
})

const ProgressStub = defineComponent({
  name: 'AProgress',
  props: ['percent', 'size'],
  template: '<div class="a-progress-stub">{{ percent }}</div>'
})

const buildContext = (overrides: Partial<TemplateApplyContext> = {}): TemplateApplyContext => ({
  raw: {
    post_id: 9,
    source_post_id: 77,
    task_id: 'task-template-scail2',
    media_type: 'video',
    input_file: 'uploads/motion.mp4',
    input_file_url: 'https://example.com/motion.mp4',
    task_type: 'scail2_video_replacement',
    requested_duration: 8,
    prompt: 'template prompt',
    negative_prompt: 'template negative'
  },
  source: 'gallery',
  entryEntityId: 9,
  rawEntityId: 9,
  rawTaskType: 'scail2_video_replacement',
  taskType: 'scail2_video_replacement',
  sourcePostId: 77,
  prompt: 'template prompt',
  negativePrompt: 'template negative',
  loraName: null,
  loraStrength: null,
  loraItems: [],
  inputFile: 'uploads/motion.mp4',
  inputFileUrl: 'https://example.com/motion.mp4',
  inputFiles: ['uploads/motion.mp4'],
  inputFileUrls: ['https://example.com/motion.mp4'],
  width: 512,
  height: 896,
  duration: 5,
  requestedDuration: 8,
  billingResolution: null,
  ...overrides
})

const mountPanel = (contextOverrides: Partial<TemplateApplyContext> = {}) =>
  mount(TemplateScail2VideoPanel, {
    props: {
      sessionId: 'session-1',
      context: buildContext(contextOverrides)
    },
    global: {
      plugins: [i18n],
      stubs: {
        'a-upload-dragger': UploadDraggerStub,
        'a-button': ButtonStub,
        'a-textarea': TextareaStub,
        'a-radio-group': RadioGroupStub,
        'a-radio-button': RadioButtonStub,
        'a-progress': ProgressStub,
        AUploadDragger: UploadDraggerStub,
        AButton: ButtonStub,
        ATextarea: TextareaStub,
        ARadioGroup: RadioGroupStub,
        ARadioButton: RadioButtonStub,
        AProgress: ProgressStub
      }
    }
  })

const loadMotionVideoMetadata = async (wrapper: ReturnType<typeof mountPanel>, seconds: number) => {
  const video = wrapper.find('video')
  Object.defineProperty(video.element, 'duration', {
    configurable: true,
    value: seconds
  })
  await video.trigger('loadedmetadata')
  await nextTick()
}

describe('TemplateScail2VideoPanel', () => {
  const createObjectURLMock = vi.fn(() => 'blob:reference-preview')
  const revokeObjectURLMock = vi.fn()

  beforeEach(() => {
    i18n.global.locale.value = 'zh'

    uploadFileMock.mockReset()
    uploadFileMock.mockResolvedValue({
      uploadId: 'upload-1',
      objectKey: 'uploads/reference.png'
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

  it('submits a template apply payload with reference image first and locked motion video second', async () => {
    const wrapper = mountPanel()
    await nextTick()
    await loadMotionVideoMetadata(wrapper, 12)

    const file = new File(['reference'], 'reference.png', { type: 'image/png' })
    await wrapper.findComponent(UploadDraggerStub).props('beforeUpload')(file)
    await flushPromises()

    await wrapper.findAllComponents(ButtonStub).at(-1)!.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledWith(
      {
        task_type: 'scail2_video_replacement',
        inputs: {
          images: ['uploads/reference.png', 'uploads/motion.mp4'],
          duration: 8,
          prompt: 'template prompt',
          negative_prompt: 'template negative'
        },
        priority: 0,
        is_template: true,
        source_post_id: 77
      },
      '视频换人'
    )
    expect(setSubmittedTaskIdMock).toHaveBeenCalledWith('task-456')
  })

  it('only exposes 5s when the template motion video is shorter than 8s', async () => {
    const wrapper = mountPanel()
    await nextTick()
    await loadMotionVideoMetadata(wrapper, 6)

    expect(wrapper.findAllComponents(RadioButtonStub).map(button => button.text())).toEqual(['5 秒'])

    const file = new File(['reference'], 'reference.png', { type: 'image/png' })
    await wrapper.findComponent(UploadDraggerStub).props('beforeUpload')(file)
    await flushPromises()

    await wrapper.findAllComponents(ButtonStub).at(-1)!.trigger('click')
    await flushPromises()

    expect(submitTaskMock.mock.calls[0][0].inputs.duration).toBe(5)
  })

  it('exposes 5s and 8s when the template motion video reaches 8s', async () => {
    const wrapper = mountPanel()
    await nextTick()
    await loadMotionVideoMetadata(wrapper, 8)

    expect(wrapper.findAllComponents(RadioButtonStub).map(button => button.text())).toEqual(['5 秒', '8 秒'])
  })

  it('maps legacy long action transfer templates to merged action transfer', async () => {
    const wrapper = mountPanel({
      rawTaskType: 'scail2_action_transfer_long',
      taskType: 'scail2_action_transfer_long',
      requestedDuration: 20,
      raw: {
        ...buildContext().raw,
        task_type: 'scail2_action_transfer_long',
        requested_duration: 20
      }
    })
    await nextTick()
    await loadMotionVideoMetadata(wrapper, 20)

    expect(wrapper.findAllComponents(RadioButtonStub).map(button => button.text())).toEqual([
      '5 秒',
      '8 秒',
      '10 秒',
      '15 秒',
      '20 秒'
    ])

    const file = new File(['reference'], 'reference.png', { type: 'image/png' })
    await wrapper.findComponent(UploadDraggerStub).props('beforeUpload')(file)
    await flushPromises()

    await wrapper.findAllComponents(ButtonStub).at(-1)!.trigger('click')
    await flushPromises()

    expect(submitTaskMock.mock.calls[0][0]).toMatchObject({
      task_type: 'scail2_action_transfer',
      inputs: {
        images: ['uploads/reference.png', 'uploads/motion.mp4'],
        duration: 20
      }
    })
  })

  it('disables submission when the template has no reusable motion video', async () => {
    const wrapper = mountPanel({
      inputFile: null,
      inputFileUrl: null,
      inputFiles: [],
      inputFileUrls: []
    })
    await nextTick()

    const file = new File(['reference'], 'reference.png', { type: 'image/png' })
    await wrapper.findComponent(UploadDraggerStub).props('beforeUpload')(file)
    await flushPromises()

    expect(wrapper.findAllComponents(ButtonStub).at(-1)!.props('disabled')).toBe(true)
    expect(submitTaskMock).not.toHaveBeenCalled()
  })

  it('renders product-facing copy and constrained upload cards', async () => {
    const wrapper = mountPanel()
    await nextTick()

    expect(wrapper.text()).toContain('已加载视频模板')
    expect(wrapper.text()).not.toContain('SCAIL')
    expect(wrapper.findAll('.scail2-template-card')).toHaveLength(2)
    expect(wrapper.find('.template-upload').classes()).toEqual(
      expect.arrayContaining(['w-full', 'min-w-0', 'overflow-hidden'])
    )
  })

  it('renders the face swap v2 task title for SCAIL-2 face swap templates', async () => {
    const wrapper = mountPanel({
      rawTaskType: 'scail2_face_swap_v2',
      taskType: 'scail2_face_swap_v2',
      raw: {
        ...buildContext().raw,
        task_type: 'scail2_face_swap_v2'
      }
    })
    await nextTick()

    expect(wrapper.text()).toContain('视频换脸')
  })
})
