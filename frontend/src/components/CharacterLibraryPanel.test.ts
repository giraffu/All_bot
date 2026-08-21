// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterLibraryPanel from './CharacterLibraryPanel.vue'

const {
  confirm,
  error,
  refresh,
  remove,
  rename,
  storeItems,
  updateViewDetails,
} = vi.hoisted(() => ({
  confirm: vi.fn(),
  error: vi.fn(),
  refresh: vi.fn(),
  remove: vi.fn(),
  rename: vi.fn(),
  storeItems: [] as any[],
  updateViewDetails: vi.fn(),
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => reactive({
    items: storeItems,
    loading: false,
    viewTemplates: [],
    refresh,
    applyViewTemplate: vi.fn(),
    generateView: vi.fn(),
    saveReference: vi.fn(),
    uploadView: vi.fn(),
    updateViewDetails,
    remove,
    rename,
  }),
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({
    uploading: ref(false),
    uploadFile: vi.fn(),
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error,
    success: vi.fn(),
  },
  Modal: {
    confirm,
  },
}))

const ButtonStub = defineComponent({
  name: 'AButton',
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: `
    <button
      v-bind="$attrs"
      :disabled="disabled"
      @click="$emit('click')"
    ><slot /></button>
  `,
})

const InputStub = defineComponent({
  name: 'AInput',
  props: ['value'],
  emits: ['update:value'],
  template: `
    <input
      v-bind="$attrs"
      :value="value"
      @input="$emit('update:value', $event.target.value)"
    />
  `,
})

const TextareaStub = defineComponent({
  name: 'ATextarea',
  props: ['value'],
  emits: ['update:value'],
  template: `
    <textarea
      v-bind="$attrs"
      :value="value"
      @input="$emit('update:value', $event.target.value)"
    />
  `,
})

const ModalStub = defineComponent({
  name: 'AModal',
  props: ['open', 'confirmLoading', 'footer'],
  emits: ['ok', 'cancel', 'update:open'],
  template: `
    <section v-if="open" data-testid="edit-character-dialog">
      <slot />
      <button v-if="footer !== null" data-testid="confirm-edit-character" @click="$emit('ok')">ok</button>
    </section>
  `,
})

describe('CharacterLibraryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refresh.mockResolvedValue(undefined)
    rename.mockResolvedValue(undefined)
    remove.mockResolvedValue(undefined)
    storeItems.splice(0, storeItems.length, {
      id: 'character-1',
      name: '鹿小草',
      description: '旧描述',
      status: 'ready',
      task_id: null,
      source_object_key: 'source.png',
      sheet_object_key: 'sheet.png',
      preview_url: 'preview.png',
      adult_confirmed: false,
      usage_rights_confirmed: false,
      prompt_profile: null,
      view_configs: [
        { type: 'face_front', label: '正脸图', can_generate: true, has_templates: false, custom: false },
        { type: 'body_front_nude', label: '裸体正面全身', can_generate: true, has_templates: false, custom: false },
        { type: 'body_front_clothed', label: '穿衣正面全身', can_generate: true, has_templates: false, custom: false },
        { type: 'torso_front', label: '胸部镜头', can_generate: false, has_templates: true, custom: false },
        { type: 'genitals_front', label: '正面私处', can_generate: false, has_templates: true, custom: false },
        { type: 'pelvis_back', label: '背面私处', can_generate: false, has_templates: true, custom: false },
        { type: 'custom_1', label: '扩展子图 1', can_generate: false, has_templates: false, custom: true },
        { type: 'custom_2', label: '扩展子图 2', can_generate: false, has_templates: false, custom: true },
        { type: 'custom_3', label: '扩展子图 3', can_generate: false, has_templates: false, custom: true },
        { type: 'custom_4', label: '扩展子图 4', can_generate: false, has_templates: false, custom: true },
      ],
      views: [
        {
          type: 'face_front',
          label: '正脸图',
          status: 'ready',
          object_key: 'face-front.png',
          preview_url: 'face-front.png',
          prompt: 'face prompt',
          default_prompt: 'default face prompt',
        },
        {
          type: 'body_front_nude',
          label: '裸体正面全身',
          status: 'ready',
          object_key: 'body-front.png',
          preview_url: 'body-front.png',
          prompt: 'front prompt',
          default_prompt: 'default front prompt',
        },
        {
          type: 'body_front_clothed',
          label: '穿衣正面全身',
          status: 'ready',
          object_key: 'body-side.png',
          preview_url: 'body-side.png',
          prompt: 'side prompt',
          default_prompt: 'default side prompt',
        },
      ],
    })
  })

  const mountPanel = () => mount(CharacterLibraryPanel, {
    global: {
      stubs: {
        AButton: ButtonStub,
        AInput: InputStub,
        ATextarea: TextareaStub,
        AModal: ModalStub,
        AUpload: { template: '<div><slot /></div>' },
        ASpin: true,
        ARadioGroup: true,
        ARadioButton: true,
      },
    },
  })

  it('uses the front-face view as a compact cover and opens all optional slots on demand', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="character-cover-character-1"]').attributes('src')).toBe('face-front.png')
    expect(wrapper.find('[data-testid="character-detail-dialog"]').exists()).toBe(false)

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')

    expect(wrapper.get('[data-testid="character-detail-dialog"]').isVisible()).toBe(true)
    expect(wrapper.findAll('[data-testid^="character-detail-view-"]').length).toBeGreaterThanOrEqual(7)
    expect(wrapper.find('[data-testid="edit-character-character-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="delete-character-character-1"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="character-view-prompt"]').element as HTMLTextAreaElement).value).toBe('face prompt')

    await wrapper.get('[data-testid="character-detail-view-body_front_clothed"]').trigger('click')

    expect((wrapper.get('[data-testid="character-view-prompt"]').element as HTMLTextAreaElement).value).toBe('side prompt')
  })

  it('edits both character name and description from the library card', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-name"]').setValue('鹿小草新版')
    await wrapper.get('[data-testid="edit-character-description"]').setValue('新描述')
    await wrapper.get('[data-testid="confirm-edit-character"]').trigger('click')
    await flushPromises()

    expect(rename).toHaveBeenCalledWith('character-1', {
      name: '鹿小草新版',
      description: '新描述',
    })
  })

  it('adds the per-view name and description after the character exists', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="character-view-display-name"]').setValue('身份正脸')
    await wrapper.get('[data-testid="character-view-description"]').setValue('短发与蓝色眼睛')
    await wrapper.get('[data-testid="save-character-view-details"]').trigger('click')

    expect(updateViewDetails).toHaveBeenCalledWith('character-1', 'face_front', {
      display_name: '身份正脸',
      description: '短发与蓝色眼睛',
    })
  })

  it('allows an empty optional character description', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-description"]').setValue('   ')
    await wrapper.get('[data-testid="confirm-edit-character"]').trigger('click')

    expect(rename).toHaveBeenCalledWith('character-1', {
      name: '鹿小草',
      description: '',
    })
  })

  it('requires confirmation before deleting a character from the library card', async () => {
    confirm.mockImplementation(({ onOk }) => onOk())
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="delete-character-character-1"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(remove).toHaveBeenCalledWith('character-1')
  })

  it('does not show a page-level identity confirmation for legacy characters', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    expect(wrapper.find('[data-testid="confirm-character-identity"]').exists()).toBe(false)
  })
})
