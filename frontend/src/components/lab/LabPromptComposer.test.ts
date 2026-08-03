// @vitest-environment jsdom

import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import LabPromptComposer from '@/components/lab/LabPromptComposer.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => ({
      'app.credits': '灵石',
      'lab.workbench.remove_asset': '移除素材',
      'lab.workbench.replace_asset': '重新上传',
      'lab.workbench.more_settings': '更多设置',
      'lab.workbench.advanced_title': '高级设置',
      'lab.workbench.optimize_prompt': '优化提示词',
    }[key] ?? key),
  }),
}))

vi.mock('@/composables/useViewport', () => ({
  useViewport: () => ({
    isMobile: ref(false),
  }),
}))

vi.mock('@ant-design/icons-vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const stub = (name: string) => defineComponent({
    name,
    template: `<span class="${name}" />`,
  })

  return {
    ArrowUpOutlined: stub('arrow-up-icon'),
    CloseOutlined: stub('close-icon'),
    EllipsisOutlined: stub('ellipsis-icon'),
    LockOutlined: stub('lock-icon'),
    PictureOutlined: stub('picture-icon'),
    PlusOutlined: stub('plus-icon'),
    ThunderboltOutlined: stub('thunderbolt-icon'),
    UndoOutlined: stub('undo-icon'),
    VideoCameraOutlined: stub('video-icon'),
  }
})

const TextareaStub = defineComponent({
  name: 'ATextarea',
  props: {
    value: { type: String, default: '' },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:value'],
  setup(props, { emit }) {
    return () => h('textarea', {
      class: 'a-textarea-stub',
      value: props.value,
      placeholder: props.placeholder,
      onInput: (event: Event) => emit('update:value', (event.target as HTMLTextAreaElement).value),
    })
  },
})

const ButtonStub = defineComponent({
  name: 'AButton',
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const mountComposer = (overrides: Partial<InstanceType<typeof LabPromptComposer>['$props']> = {}) => mount(LabPromptComposer, {
  props: {
    title: '动作迁移',
    description: '上传参考图和驱动视频。',
    promptPlaceholder: '可以写角色风格、服装、画面氛围，也可以留空。',
    prompt: '',
    promptLocked: false,
    showStructuredPromptInput: true,
    references: [],
    assetUploadSlots: [
      {
        id: 'reference_image',
        label: '参考图片',
        hint: '上传参考角色',
        buttonLabel: '参考图片',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
        item: null,
      },
      {
        id: 'motion_video',
        label: '驱动视频',
        hint: '上传动作视频',
        buttonLabel: '驱动视频',
        accept: 'video/mp4,video/quicktime,video/webm',
        previewKind: 'video',
        required: true,
        item: null,
      },
    ],
    referenceTitle: '',
    supportsUpload: false,
    canUploadReference: false,
    uploadButtonLabel: '添加参考图',
    beforeUpload: vi.fn(),
    beforeUploadSlot: vi.fn(),
    submitText: '生成视频',
    submitDisabled: false,
    submitLoading: false,
    cost: 40,
    hasAdvancedOptions: false,
    ...overrides,
  },
  global: {
    stubs: {
      LabReferenceTray: true,
      'a-button': ButtonStub,
      'a-drawer': true,
      'a-popover': true,
      'a-progress': true,
      'a-textarea': TextareaStub,
      'a-upload': { template: '<div class="a-upload-stub"><slot /></div>' },
    },
  },
})

describe('LabPromptComposer structured uploads', () => {
  it('shows one optimizer action without a redundant template selector', () => {
    const wrapper = mountComposer({
      showPromptOptimizer: true,
      optimizePromptDisabled: false,
    })

    expect(wrapper.text()).toContain('优化提示词')
    expect(wrapper.findComponent({ name: 'ASelect' }).exists()).toBe(false)
  })

  it('shows an optional prompt input below structured upload slots when enabled', async () => {
    const wrapper = mountComposer()

    const textarea = wrapper.get('textarea.a-textarea-stub')
    expect(textarea.attributes('placeholder')).toBe('可以写角色风格、服装、画面氛围，也可以留空。')

    await textarea.setValue('保留古风服装，镜头自然')

    expect(wrapper.emitted('update:prompt')).toEqual([['保留古风服装，镜头自然']])
  })

  it('keeps the prompt input hidden for upload-slot modes that do not opt in', () => {
    const wrapper = mountComposer({
      showStructuredPromptInput: false,
    })

    expect(wrapper.find('textarea.a-textarea-stub').exists()).toBe(false)
  })
})
