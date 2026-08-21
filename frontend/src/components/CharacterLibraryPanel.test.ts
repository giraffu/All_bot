// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterLibraryPanel from './CharacterLibraryPanel.vue'

const {
  confirm,
  confirmIdentity,
  error,
  refresh,
  remove,
  rename,
  storeItems,
} = vi.hoisted(() => ({
  confirm: vi.fn(),
  confirmIdentity: vi.fn(),
  error: vi.fn(),
  refresh: vi.fn(),
  remove: vi.fn(),
  rename: vi.fn(),
  storeItems: [] as any[],
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => reactive({
    items: storeItems,
    loading: false,
    refresh,
    confirmIdentity,
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
    confirmIdentity.mockResolvedValue(undefined)
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
      views: [
        {
          type: 'face_front',
          label: '正脸图',
          status: 'ready',
          preview_url: 'face-front.png',
          prompt: 'face prompt',
          default_prompt: 'default face prompt',
        },
        {
          type: 'body_front',
          label: '全身正面图',
          status: 'ready',
          preview_url: 'body-front.png',
          prompt: 'front prompt',
          default_prompt: 'default front prompt',
        },
        {
          type: 'body_side',
          label: '全身侧面图',
          status: 'ready',
          preview_url: 'body-side.png',
          prompt: 'side prompt',
          default_prompt: 'default side prompt',
        },
        {
          type: 'body_back',
          label: '全身背面图',
          status: 'ready',
          preview_url: 'body-back.png',
          prompt: 'back prompt',
          default_prompt: 'default back prompt',
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

  it('uses the front-face view as a compact cover and opens four-view management on demand', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="character-cover-character-1"]').attributes('src')).toBe('face-front.png')
    expect(wrapper.find('[data-testid="character-detail-dialog"]').exists()).toBe(false)

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')

    expect(wrapper.get('[data-testid="character-detail-dialog"]').isVisible()).toBe(true)
    expect(wrapper.findAll('[data-testid^="character-detail-view-"]')).toHaveLength(4)
    expect(wrapper.find('[data-testid="edit-character-character-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="delete-character-character-1"]').exists()).toBe(true)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('face prompt')

    await wrapper.get('[data-testid="character-detail-view-body_side"]').trigger('click')

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('side prompt')
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

  it('does not save an empty character description', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="edit-character-description"]').setValue('   ')
    await wrapper.get('[data-testid="confirm-edit-character"]').trigger('click')

    expect(rename).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledWith('characters.description_required')
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

  it('requires a one-time identity confirmation for legacy characters', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-character-character-1"]').trigger('click')
    await wrapper.get('[data-testid="confirm-character-identity"]').trigger('click')
    await flushPromises()

    expect(confirmIdentity).toHaveBeenCalledWith('character-1', { gender: 'female' })
  })
})
