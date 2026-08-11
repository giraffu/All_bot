// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateImagePromptPanel from '@/components/template-apply/TemplateImagePromptPanel.vue'
import type { TemplateApplyContext } from '@/types/templateApply'

const {
  sharedRefs,
  templateApplyStoreMock,
  setSubmittedTaskIdMock,
  downloadResultMock,
  submitTaskMock,
  uploadFileMock
} = vi.hoisted(() => ({
  sharedRefs: {
    hasPendingUploadsRef: undefined as any,
    uploadingSlotsRef: undefined as any,
    progressBySlotRef: undefined as any,
    isSubmittingRef: undefined as any,
    currentTaskRef: undefined as any
  },
  templateApplyStoreMock: {
    setPendingUploads: vi.fn(),
    setDirtyState: vi.fn(),
    registerPanelController: vi.fn(),
    closeAfterSubmission: vi.fn()
  },
  setSubmittedTaskIdMock: vi.fn(),
  downloadResultMock: vi.fn(),
  submitTaskMock: vi.fn(),
  uploadFileMock: vi.fn()
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
      isVideoUrl: vi.fn(() => false),
      downloadResult: downloadResultMock
    })
  }
})

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock
}))

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
    InboxOutlined: stub('inbox-icon')
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
  props: ['value'],
  template: '<button class="a-radio-button-stub"><slot /></button>'
})

const TextareaStub = defineComponent({
  name: 'ATextarea',
  props: ['value', 'rows', 'placeholder'],
  emits: ['update:value'],
  template: '<textarea class="a-textarea-stub" :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
})

const SliderStub = defineComponent({
  name: 'ASlider',
  props: ['value', 'min', 'max', 'step'],
  emits: ['update:value'],
  template: '<div class="a-slider-stub" />'
})

const buildContext = (overrides: Record<string, unknown> = {}): TemplateApplyContext => ({
  raw: {
    post_id: 1,
    source_post_id: 91,
    task_id: 'task-template-edit',
    media_type: 'image',
    task_type: 'edit',
    prompt: 'preset prompt',
    lora_name: 'qwen/YARN_1.0.safetensors',
    lora_strength: 0.3
  },
  source: 'gallery',
  entryEntityId: 1,
  rawEntityId: 1,
  rawTaskType: 'edit',
  taskType: 'edit',
  sourcePostId: 91,
  prompt: 'preset prompt',
  negativePrompt: null,
  loraName: 'qwen/YARN_1.0.safetensors',
  loraStrength: 0.3,
  loraItems: [],
  inputFile: null,
  inputFileUrl: null,
  width: 512,
  height: 512,
  duration: null,
  requestedDuration: null,
  billingResolution: null,
  ...overrides
})

const mountPanel = (context: TemplateApplyContext) => mount(TemplateImagePromptPanel, {
  props: {
    sessionId: 'session-1',
    context
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
      'a-slider': SliderStub,
      AUploadDragger: UploadDraggerStub,
      AButton: ButtonStub,
      AProgress: ProgressStub,
      ARadioGroup: RadioGroupStub,
      ARadioButton: RadioButtonStub,
      ATextarea: TextareaStub,
      ASlider: SliderStub
    }
  }
})

describe('TemplateImagePromptPanel', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:test-image'),
      configurable: true
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: vi.fn(),
      configurable: true
    })
    sharedRefs.hasPendingUploadsRef.value = false
    sharedRefs.uploadingSlotsRef.value = {}
    sharedRefs.progressBySlotRef.value = {}
    sharedRefs.isSubmittingRef.value = false
    sharedRefs.currentTaskRef.value = null
    templateApplyStoreMock.setPendingUploads.mockReset()
    templateApplyStoreMock.setDirtyState.mockReset()
    templateApplyStoreMock.registerPanelController.mockReset()
    templateApplyStoreMock.closeAfterSubmission.mockReset()
    setSubmittedTaskIdMock.mockReset()
    downloadResultMock.mockReset()
    submitTaskMock.mockReset()
    uploadFileMock.mockReset()
  })

  it('hides prompt and locked addon controls for template edit apply', async () => {
    const wrapper = mountPanel(buildContext())

    await nextTick()

    expect(wrapper.text()).toContain('已加载一键应用模板')
    expect(wrapper.findComponent(TextareaStub).exists()).toBe(false)
    expect(wrapper.findComponent(RadioGroupStub).exists()).toBe(false)
  })

  it('closes the template workbench after a task is submitted', async () => {
    const wrapper = mountPanel(buildContext())
    await nextTick()

    const beforeUpload = wrapper.findComponent(UploadDraggerStub).props('beforeUpload') as (file: File) => Promise<boolean>
    uploadFileMock.mockResolvedValueOnce({ objectKey: 'base.png' })
    submitTaskMock.mockResolvedValueOnce('task-789')
    await beforeUpload(new File(['base'], 'base.png', { type: 'image/png' }))
    await nextTick()

    await wrapper.findComponent(ButtonStub).trigger('click')
    await flushPromises()

    expect(setSubmittedTaskIdMock).toHaveBeenCalledWith('task-789')
    expect(templateApplyStoreMock.closeAfterSubmission).toHaveBeenCalledWith('session-1')
  })

  it('applies historical free edit templates through v3 with one image and no addon model', async () => {
    const wrapper = mountPanel(buildContext({
      raw: {
        post_id: 2,
        source_post_id: 92,
        task_id: 'task-template-v2',
        media_type: 'image',
        task_type: 'pornmaster_flux2_single_edit',
        prompt: 'clean up details',
        lora_name: 'qwen/YARN_1.0.safetensors',
        lora_strength: 0.3
      },
      rawTaskType: 'pornmaster_flux2_single_edit',
      taskType: 'pornmaster_flux2_edit_bf16',
      sourcePostId: 92,
      prompt: 'clean up details',
      loraName: 'qwen/YARN_1.0.safetensors',
      loraStrength: 0.3,
    }))
    await nextTick()

    expect(wrapper.text()).toContain('自由P图 v3')
    expect(wrapper.findComponent(RadioGroupStub).exists()).toBe(false)

    const beforeUpload = wrapper.findComponent(UploadDraggerStub).props('beforeUpload') as (file: File) => Promise<boolean>
    uploadFileMock.mockResolvedValueOnce({ objectKey: 'base.png' })
    await beforeUpload(new File(['base'], 'base.png', { type: 'image/png' }))
    await nextTick()

    await wrapper.findComponent(ButtonStub).trigger('click')
    await flushPromises()

    const payload = submitTaskMock.mock.calls[0][0]
    expect(payload).toMatchObject({
      task_type: 'pornmaster_flux2_edit_bf16',
      inputs: {
        images: ['base.png'],
      },
      prompt: 'clean up details',
      is_template: true,
      source_post_id: 92,
    })
    expect(payload.inputs).not.toHaveProperty('lora_name')
    expect(payload.inputs).not.toHaveProperty('lora_strength')

    submitTaskMock.mockClear()
    uploadFileMock.mockResolvedValueOnce({ objectKey: 'style.png' })
    await beforeUpload(new File(['style'], 'style.png', { type: 'image/png' }))
    await nextTick()
    expect(uploadFileMock).toHaveBeenCalledTimes(1)
  })

  it('applies free edit v2.5 templates as a three-credit single-image task', async () => {
    const wrapper = mountPanel(buildContext({
      raw: {
        post_id: 25,
        source_post_id: 25,
        task_id: 'task-template-v2-5',
        media_type: 'image',
        task_type: 'free_edit_v2_5',
        prompt: 'keep the original prompt',
        lora_name: 'qwen/YARN_1.0.safetensors',
      },
      rawTaskType: 'free_edit_v2_5',
      taskType: 'free_edit_v2_5',
      sourcePostId: 25,
      prompt: 'keep the original prompt',
      loraName: 'qwen/YARN_1.0.safetensors',
    }))
    await nextTick()

    expect(wrapper.text()).toContain('自由P图 v2.5')
    expect(wrapper.findComponent(TextareaStub).exists()).toBe(false)
    expect(wrapper.findComponent(RadioGroupStub).exists()).toBe(false)

    const beforeUpload = wrapper.findComponent(UploadDraggerStub).props('beforeUpload') as (file: File) => Promise<boolean>
    uploadFileMock.mockResolvedValueOnce({ objectKey: 'replacement.png' })
    await beforeUpload(new File(['replacement'], 'replacement.png', { type: 'image/png' }))
    await nextTick()

    await wrapper.findComponent(ButtonStub).trigger('click')
    await flushPromises()

    expect(submitTaskMock.mock.calls[0][0]).toMatchObject({
      task_type: 'free_edit_v2_5',
      inputs: {
        images: ['replacement.png'],
      },
      prompt: 'keep the original prompt',
      is_template: true,
      source_post_id: 25,
    })
    expect(submitTaskMock.mock.calls[0][0].inputs).not.toHaveProperty('lora_name')

    uploadFileMock.mockResolvedValueOnce({ objectKey: 'second.png' })
    await beforeUpload(new File(['second'], 'second.png', { type: 'image/png' }))
    expect(uploadFileMock).toHaveBeenCalledTimes(1)
  })

  it('requires two new images for a dual-image v2.5 template', async () => {
    const wrapper = mountPanel(buildContext({
      raw: {
        post_id: 26,
        source_post_id: 26,
        task_id: 'task-template-v2-5-dual',
        media_type: 'image',
        task_type: 'free_edit_v2_5',
        prompt: 'combine both references',
        required_image_count: 2,
      },
      rawTaskType: 'free_edit_v2_5',
      taskType: 'free_edit_v2_5',
      sourcePostId: 26,
      prompt: 'combine both references',
      requiredImageCount: 2,
    }))
    await nextTick()

    const beforeUpload = wrapper.findComponent(UploadDraggerStub).props('beforeUpload') as (file: File) => Promise<boolean>
    uploadFileMock
      .mockResolvedValueOnce({ objectKey: 'replacement-one.png' })
      .mockResolvedValueOnce({ objectKey: 'replacement-two.png' })
    await beforeUpload(new File(['one'], 'one.png', { type: 'image/png' }))
    await nextTick()

    await wrapper.findComponent(ButtonStub).trigger('click')
    await flushPromises()
    expect(submitTaskMock).not.toHaveBeenCalled()

    await beforeUpload(new File(['two'], 'two.png', { type: 'image/png' }))
    await nextTick()
    await wrapper.findComponent(ButtonStub).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('7')
    expect(submitTaskMock.mock.calls[0][0]).toMatchObject({
      task_type: 'free_edit_v2_5',
      inputs: {
        images: ['replacement-one.png', 'replacement-two.png'],
      },
      prompt: 'combine both references',
      is_template: true,
      source_post_id: 26,
    })
  })
})
