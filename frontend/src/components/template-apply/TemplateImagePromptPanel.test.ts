// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
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
    registerPanelController: vi.fn()
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
  supportMode: 'workbench',
  sourcePostId: 91,
  prompt: 'preset prompt',
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

describe('TemplateImagePromptPanel', () => {
  beforeEach(() => {
    sharedRefs.hasPendingUploadsRef.value = false
    sharedRefs.uploadingSlotsRef.value = {}
    sharedRefs.progressBySlotRef.value = {}
    sharedRefs.isSubmittingRef.value = false
    sharedRefs.currentTaskRef.value = null
    templateApplyStoreMock.setPendingUploads.mockReset()
    templateApplyStoreMock.setDirtyState.mockReset()
    templateApplyStoreMock.registerPanelController.mockReset()
    setSubmittedTaskIdMock.mockReset()
    downloadResultMock.mockReset()
    submitTaskMock.mockReset()
    uploadFileMock.mockReset()
  })

  it('hides prompt and locked addon controls for template edit apply', async () => {
    const wrapper = mount(TemplateImagePromptPanel, {
      props: {
        sessionId: 'session-1',
        context: buildContext()
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

    await nextTick()

    expect(wrapper.text()).toContain('已加载一键应用模板')
    expect(wrapper.findComponent(TextareaStub).exists()).toBe(false)
    expect(wrapper.findComponent(RadioGroupStub).exists()).toBe(false)
  })
})
