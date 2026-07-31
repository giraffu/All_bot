// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterLibraryPanel from './CharacterLibraryPanel.vue'

const {
  confirm,
  refresh,
  remove,
  rename,
  storeItems,
} = vi.hoisted(() => ({
  confirm: vi.fn(),
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
    remove,
    rename,
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
    error: vi.fn(),
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
  props: ['open', 'confirmLoading'],
  emits: ['ok', 'cancel', 'update:open'],
  template: `
    <section v-if="open" data-testid="edit-character-dialog">
      <slot />
      <button data-testid="confirm-edit-character" @click="$emit('ok')">ok</button>
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
      views: [],
    })
  })

  const mountPanel = () => mount(CharacterLibraryPanel, {
    global: {
      stubs: {
        AButton: ButtonStub,
        AInput: InputStub,
        ATextarea: TextareaStub,
        AModal: ModalStub,
        ASpin: true,
        ARadioGroup: true,
        ARadioButton: true,
      },
    },
  })

  it('edits both character name and description from the library card', async () => {
    const wrapper = mountPanel()
    await flushPromises()

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

  it('requires confirmation before deleting a character from the library card', async () => {
    confirm.mockImplementation(({ onOk }) => onOk())
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="delete-character-character-1"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(remove).toHaveBeenCalledWith('character-1')
  })
})
