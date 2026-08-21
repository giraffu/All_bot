// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterReferenceWorkbench from './CharacterReferenceWorkbench.vue'

const mocks = vi.hoisted(() => ({
  applyViewTemplate: vi.fn(),
  createDraft: vi.fn(),
  generateView: vi.fn(),
  refresh: vi.fn(),
  rename: vi.fn(),
  saveReference: vi.fn(),
  updateViewDetails: vi.fn(),
  uploadFile: vi.fn(),
  uploadView: vi.fn(),
  items: [] as any[],
  templates: [] as any[],
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => reactive({
    items: mocks.items,
    viewTemplates: mocks.templates,
    applyViewTemplate: mocks.applyViewTemplate,
    createDraft: mocks.createDraft,
    generateView: mocks.generateView,
    refresh: mocks.refresh,
    rename: mocks.rename,
    saveReference: mocks.saveReference,
    updateViewDetails: mocks.updateViewDetails,
    uploadView: mocks.uploadView,
  }),
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({ uploading: ref(false), uploadFile: mocks.uploadFile }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

const PassThrough = defineComponent({ template: '<div><slot /></div>' })
const ButtonStub = defineComponent({
  props: ['disabled'],
  emits: ['click'],
  template: '<button v-bind="$attrs" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

const mountWorkbench = () => mount(CharacterReferenceWorkbench, {
  global: {
    stubs: {
      AButton: ButtonStub,
      AInput: PassThrough,
      ATextarea: PassThrough,
      ARadioGroup: PassThrough,
      ARadioButton: PassThrough,
      AUpload: PassThrough,
      ASelect: PassThrough,
      ASelectOption: PassThrough,
    },
  },
})

describe('CharacterReferenceWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.templates.splice(0, mocks.templates.length, {
      id: 'template-1',
      view_type: 'genitals_front',
      name: '管理员模板 A',
      gender: 'female',
      sort_order: 10,
      preview_url: 'template.png',
    })
    mocks.items.splice(0, mocks.items.length, {
      id: 'character-1',
      name: 'Alice',
      description: null,
      status: 'ready',
      preview_url: 'sheet.png',
      default_prompts: {
        face_front: 'face prompt',
        body_front_nude: 'nude prompt',
        body_front_clothed: 'clothed prompt',
      },
      view_configs: [
        { type: 'face_front', label: '正脸', can_generate: true, has_templates: false, custom: false },
        { type: 'body_front_nude', label: '裸体正面全身', can_generate: true, has_templates: false, custom: false },
        { type: 'body_front_clothed', label: '穿衣正面全身', can_generate: true, has_templates: false, custom: false },
        { type: 'torso_front', label: '胸部镜头', can_generate: false, has_templates: true, custom: false },
        { type: 'genitals_front', label: '正面私处', can_generate: false, has_templates: true, custom: false },
        { type: 'pelvis_back', label: '背面私处', can_generate: false, has_templates: true, custom: false },
        { type: 'custom_1', label: '扩展子图 1', can_generate: false, has_templates: false, custom: true },
      ],
      views: [{
        type: 'face_front', label: '正脸', description: null, prompt: 'face prompt',
        default_prompt: 'face prompt', status: 'ready', preview_url: 'face.png', object_key: 'face.png',
      }],
    })
    mocks.refresh.mockResolvedValue(undefined)
    mocks.createDraft.mockResolvedValue(mocks.items[0])
    mocks.uploadFile.mockResolvedValue('web_uploads/123/detail.png')
  })

  it('creates from any upload-only slot without page-level confirmations', async () => {
    const wrapper = mountWorkbench()
    ;(wrapper.vm as any).name = '脚部人物素材'
    ;(wrapper.vm as any).initialViewType = 'custom_1'
    ;(wrapper.vm as any).initialViewLabel = '脚部特写'
    ;(wrapper.vm as any).initialSourceKey = 'web_uploads/123/feet.png'

    await (wrapper.vm as any).createDraft()

    expect(wrapper.text()).not.toContain('18+')
    expect(mocks.createDraft).toHaveBeenCalledWith({
      name: '脚部人物素材',
      initial_view_type: 'custom_1',
      initial_view_label: '脚部特写',
      source_object_key: 'web_uploads/123/feet.png',
      template_id: undefined,
    })
  })

  it('applies one of multiple admin templates to a body-detail slot', async () => {
    const wrapper = mountWorkbench()
    ;(wrapper.vm as any).draftId = 'character-1'
    ;(wrapper.vm as any).activeViewType = 'genitals_front'
    await nextTick()
    ;(wrapper.vm as any).selectedTemplateId = 'template-1'

    await (wrapper.vm as any).applyTemplate()

    expect(mocks.applyViewTemplate).toHaveBeenCalledWith(
      'character-1',
      'genitals_front',
      'template-1',
    )
  })

  it('uploads a replacement and only exposes generation for configured base views', async () => {
    const wrapper = mountWorkbench()
    ;(wrapper.vm as any).draftId = 'character-1'
    ;(wrapper.vm as any).activeViewType = 'genitals_front'
    await nextTick()

    const file = new File(['detail'], 'detail.png', { type: 'image/png' })
    await (wrapper.vm as any).beforeViewUpload(file)

    expect(mocks.uploadView).toHaveBeenCalledWith('character-1', 'genitals_front', 'web_uploads/123/detail.png')
    expect((wrapper.vm as any).activeConfig.can_generate).toBe(false)
    ;(wrapper.vm as any).activeViewType = 'face_front'
    await nextTick()
    expect((wrapper.vm as any).activeConfig.can_generate).toBe(true)
  })
})
