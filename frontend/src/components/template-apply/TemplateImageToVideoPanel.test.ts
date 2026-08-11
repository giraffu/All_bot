// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateImageToVideoPanel from '@/components/template-apply/TemplateImageToVideoPanel.vue'
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

const TextareaStub = defineComponent({
  name: 'ATextarea',
  props: ['value', 'rows', 'placeholder'],
  emits: ['update:value'],
  template: '<textarea class="a-textarea-stub" :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
})

const SelectStub = defineComponent({
  name: 'ASelect',
  props: ['value', 'placeholder'],
  emits: ['update:value'],
  template: '<select class="a-select-stub"><slot /></select>'
})

const SelectOptionStub = defineComponent({
  name: 'ASelectOption',
  props: ['value'],
  template: '<option class="a-select-option-stub"><slot /></option>'
})

const buildContext = (overrides: Record<string, unknown> = {}): TemplateApplyContext => ({
  raw: {
    post_id: 1,
    source_post_id: 77,
    task_id: 'task-template-video',
    media_type: 'video',
    task_type: 'custom_video',
    prompt: 'cinematic action shot',
    width: 720,
    height: 1280,
    duration: 8,
    billing_resolution: '720'
  },
  source: 'gallery',
  entryEntityId: 1,
  rawEntityId: 1,
  rawTaskType: 'custom_video',
  taskType: 'custom_video',
  sourcePostId: 77,
  prompt: 'cinematic action shot',
  negativePrompt: null,
  loraName: null,
  loraStrength: null,
  loraItems: [],
  inputFile: null,
  inputFileUrl: null,
  width: 720,
  height: 1280,
  duration: 8,
  requestedDuration: null,
  billingResolution: '720',
  ...overrides
})

const mountPanel = (contextOverrides: Record<string, unknown> = {}) =>
  mount(TemplateImageToVideoPanel, {
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
        'a-textarea': TextareaStub,
        'a-select': SelectStub,
        'a-select-option': SelectOptionStub,
        AUploadDragger: UploadDraggerStub,
        AButton: ButtonStub,
        AProgress: ProgressStub,
        ARadioGroup: RadioGroupStub,
        ARadioButton: RadioButtonStub,
        ATextarea: TextareaStub,
        ASelect: SelectStub,
        ASelectOption: SelectOptionStub
      }
    }
  })

describe('TemplateImageToVideoPanel', () => {
  const createObjectURLMock = vi.fn(() => 'blob:base-preview')
  const revokeObjectURLMock = vi.fn()

  beforeEach(() => {
    uploadFileMock.mockReset()
    uploadFileMock.mockResolvedValue({
      uploadId: 'upload-1',
      objectKey: 'uploads/base.png'
    })

    sharedRefs.hasPendingUploadsRef.value = false
    sharedRefs.uploadingSlotsRef.value = {}
    sharedRefs.progressBySlotRef.value = {}

    submitTaskMock.mockReset()
    submitTaskMock.mockResolvedValue('task-789')
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

  it('submits the expected template payload for custom_video', async () => {
    const wrapper = mountPanel()
    await nextTick()

    expect(wrapper.text()).toContain('已加载一键应用模板')
    expect(wrapper.findComponent(TextareaStub).exists()).toBe(false)
    expect(wrapper.findAllComponents(RadioGroupStub)).toHaveLength(0)

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)

    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file, { slot: 'base_image' })
    expect(createObjectURLMock).toHaveBeenCalledWith(file)
    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'custom_video',
      inputs: {
        images: ['uploads/base.png'],
        duration: 5,
        prompt: 'cinematic action shot',
        resolution_preset: 'standard',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 77
    })
    expect(typeof submitTaskMock.mock.calls[0]?.[1]).toBe('string')
    expect(setSubmittedTaskIdMock).toHaveBeenLastCalledWith('task-789')
  })

  it('submits the expected template payload for video_lora', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 2,
        source_post_id: 88,
        task_id: 'task-template-video-lora',
        media_type: 'video',
        task_type: 'video_lora',
        prompt: 'glowing neon city',
        lora_name: 'BreastGrow',
        width: 1024,
        height: 1024,
        duration: 8,
        billing_resolution: '1024'
      },
      rawEntityId: 2,
      rawTaskType: 'video_lora',
      taskType: 'video_lora',
      sourcePostId: 88,
      prompt: 'glowing neon city',
      loraName: 'BreastGrow',
      width: 1024,
      height: 1024,
      duration: 8,
      billingResolution: '1024'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)

    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file, { slot: 'base_image' })
    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'video_lora',
      inputs: {
        images: ['uploads/base.png'],
        duration: 5,
        prompt: 'glowing neon city',
        lora_name: 'BreastGrow',
        resolution_preset: 'hd',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 88
    })
    expect(typeof submitTaskMock.mock.calls[0]?.[1]).toBe('string')
    expect(setSubmittedTaskIdMock).toHaveBeenLastCalledWith('task-789')
  })

  it('falls back to 5s when custom_video requested_duration is missing', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 4,
        source_post_id: 120,
        task_id: 'task-template-custom-video-legacy',
        media_type: 'video',
        task_type: 'custom_video',
        prompt: 'cinematic action shot',
        width: 720,
        height: 1280,
        duration: 9,
        requested_duration: null,
        billing_resolution: '720'
      },
      rawEntityId: 4,
      rawTaskType: 'custom_video',
      taskType: 'custom_video',
      sourcePostId: 120,
      prompt: 'cinematic action shot',
      width: 720,
      height: 1280,
      duration: 9,
      requestedDuration: null,
      billingResolution: '720'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'custom_video',
      inputs: {
        images: ['uploads/base.png'],
        duration: 5,
        prompt: 'cinematic action shot',
        resolution_preset: 'standard',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 120
    })
  })

  it('falls back to 5s when video_lora requested_duration is missing', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 5,
        source_post_id: 121,
        task_id: 'task-template-video-lora-legacy',
        media_type: 'video',
        task_type: 'video_lora',
        prompt: 'glowing neon city',
        lora_name: 'BreastGrow',
        width: 1024,
        height: 1024,
        duration: 11,
        requested_duration: null,
        billing_resolution: '1024'
      },
      rawEntityId: 5,
      rawTaskType: 'video_lora',
      taskType: 'video_lora',
      sourcePostId: 121,
      prompt: 'glowing neon city',
      loraName: 'BreastGrow',
      width: 1024,
      height: 1024,
      duration: 11,
      requestedDuration: null,
      billingResolution: '1024'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'video_lora',
      inputs: {
        images: ['uploads/base.png'],
        duration: 5,
        prompt: 'glowing neon city',
        lora_name: 'BreastGrow',
        resolution_preset: 'hd',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 121
    })
  })

  it('normalizes empty template lora selection to custom_video without lora_name', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 6,
        source_post_id: 122,
        task_id: 'task-template-video-lora-none',
        media_type: 'video',
        task_type: 'video_lora',
        prompt: 'gentle motion',
        lora_name: '',
        width: 720,
        height: 1280,
        duration: 8,
        billing_resolution: '720'
      },
      rawEntityId: 6,
      rawTaskType: 'video_lora',
      taskType: 'video_lora',
      sourcePostId: 122,
      prompt: 'gentle motion',
      loraName: null,
      width: 720,
      height: 1280,
      duration: 8,
      billingResolution: '720'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'custom_video',
      inputs: {
        images: ['uploads/base.png'],
        duration: 5,
        prompt: 'gentle motion',
        resolution_preset: 'standard',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 122
    })
  })

  it('submits the expected template payload for wan22_video_v2 with negative prompt', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 7,
        source_post_id: 123,
        task_id: 'task-template-wan22-v2',
        media_type: 'video',
        task_type: 'wan22_video_v2',
        prompt: 'cinematic v2 motion',
        negative_prompt: 'low quality blur',
        width: 512,
        height: 768,
        duration: 13,
        requested_duration: 10,
        billing_resolution: 'standard'
      },
      rawEntityId: 7,
      rawTaskType: 'wan22_video_v2',
      taskType: 'wan22_video_v2',
      sourcePostId: 123,
      prompt: 'cinematic v2 motion',
      negativePrompt: 'low quality blur',
      width: 512,
      height: 768,
      duration: 13,
      requestedDuration: 10,
      billingResolution: 'standard'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'wan22_video_v2',
      inputs: {
        images: ['uploads/base.png'],
        duration: 10,
        prompt: 'cinematic v2 motion',
        negative_prompt: 'low quality blur',
        resolution_preset: 'standard',
        use_end_frame: false
      },
      priority: 0,
      is_template: true,
      source_post_id: 123
    })
  })

  it('does not submit dirty legacy ltx_video media duration when requestedDuration is missing', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 3,
        source_post_id: 99,
        task_id: 'task-template-ltx-legacy',
        media_type: 'video',
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        width: 1344,
        height: 768,
        duration: 1,
        requested_duration: null,
        billing_resolution: '1344x768'
      },
      rawEntityId: 3,
      rawTaskType: 'ltx_video',
      taskType: 'ltx_video',
      sourcePostId: 99,
      prompt: 'wide cinematic dolly shot',
      width: 1344,
      height: 768,
      duration: 1,
      requestedDuration: null,
      billingResolution: '1344x768'
    })
    await nextTick()

    expect(wrapper.text()).not.toContain('模板参数已锁定')

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)

    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['uploads/base.png'],
        resolution: '1280x704',
        duration: 5,
        prompt: 'wide cinematic dolly shot',
        ltx_mode: 'i2v',
        use_end_frame: false,
        extract_last_frame: true
      },
      priority: 0,
      is_template: true,
      source_post_id: 99
    })
  })

  it('submits ltx_video template payload with optional addon model', async () => {
    const wrapper = mountPanel({
      raw: {
        post_id: 7,
        source_post_id: 123,
        task_id: 'task-template-ltx-lora',
        media_type: 'video',
        task_type: 'ltx_video',
        prompt: 'wide cinematic dolly shot',
        negative_prompt: 'low quality blur',
        lora_name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        width: 1280,
        height: 704,
        duration: 10,
        requested_duration: 10,
        billing_resolution: '1280x704'
      },
      rawEntityId: 7,
      rawTaskType: 'ltx_video',
      taskType: 'ltx_video',
      sourcePostId: 123,
      prompt: 'wide cinematic dolly shot',
      negativePrompt: 'low quality blur',
      loraName: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
      width: 1280,
      height: 704,
      duration: 10,
      requestedDuration: 10,
      billingResolution: '1280x704'
    })
    await nextTick()

    const file = new File(['base'], 'base.png', { type: 'image/png' })
    const uploader = wrapper.findComponent(UploadDraggerStub)
    await uploader.props('beforeUpload')(file)
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['uploads/base.png'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'wide cinematic dolly shot',
        negative_prompt: 'low quality blur',
        lora_name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        lora_strength: 0.8,
        lora_items: [
          {
            name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
            strength: 0.8
          }
        ],
        ltx_mode: 'i2v',
        use_end_frame: false,
        extract_last_frame: true
      },
      priority: 0,
      is_template: true,
      source_post_id: 123
    })
  })

  it('submits ltx_video template payload as first-last-frame when an end frame is uploaded', async () => {
    uploadFileMock.mockImplementation(async (_file, options) => ({
      uploadId: `upload-${options.slot}`,
      objectKey: options.slot === 'end_image' ? 'uploads/end.png' : 'uploads/start.png'
    }))

    const wrapper = mountPanel({
      raw: {
        post_id: 8,
        source_post_id: 124,
        task_id: 'task-template-ltx-flf2v',
        media_type: 'video',
        task_type: 'ltx_video',
        prompt: 'start and end cinematic move',
        width: 1280,
        height: 704,
        duration: 10,
        requested_duration: 10,
        billing_resolution: '1280x704'
      },
      rawEntityId: 8,
      rawTaskType: 'ltx_video',
      taskType: 'ltx_video',
      sourcePostId: 124,
      prompt: 'start and end cinematic move',
      width: 1280,
      height: 704,
      duration: 10,
      requestedDuration: 10,
      billingResolution: '1280x704'
    })
    await nextTick()

    expect(wrapper.text()).toContain('终止帧')

    const uploaders = wrapper.findAllComponents(UploadDraggerStub)
    expect(uploaders).toHaveLength(2)

    await uploaders[0].props('beforeUpload')(new File(['start'], 'start.png', { type: 'image/png' }))
    await uploaders[1].props('beforeUpload')(new File(['end'], 'end.png', { type: 'image/png' }))
    await flushPromises()

    const generateButton = wrapper
      .findAllComponents(ButtonStub)
      .find(button => button.text().includes('生成视频'))

    if (!generateButton) {
      throw new Error('Expected generate button to exist')
    }

    await generateButton.trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(expect.any(File), { slot: 'base_image' })
    expect(uploadFileMock).toHaveBeenCalledWith(expect.any(File), { slot: 'end_image' })
    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    expect(submitTaskMock.mock.calls[0]?.[0]).toEqual({
      task_type: 'ltx_video',
      inputs: {
        images: ['uploads/start.png', 'uploads/end.png'],
        resolution: '1280x704',
        duration: 10,
        prompt: 'start and end cinematic move',
        ltx_mode: 'flf2v',
        use_end_frame: true,
        extract_last_frame: true
      },
      priority: 0,
      is_template: true,
      source_post_id: 124
    })
  })
})
