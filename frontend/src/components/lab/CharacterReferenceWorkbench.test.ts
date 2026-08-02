// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterReferenceWorkbench from './CharacterReferenceWorkbench.vue'

const {
  createDraft,
  error,
  fetchCapacity,
  generateView,
  refresh,
  storeItems,
  uploadFile,
  uploadView,
} = vi.hoisted(() => ({
  createDraft: vi.fn(),
  error: vi.fn(),
  fetchCapacity: vi.fn(),
  generateView: vi.fn(),
  refresh: vi.fn(),
  storeItems: [] as any[],
  uploadFile: vi.fn(),
  uploadView: vi.fn(),
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => reactive({
    items: storeItems,
    refresh,
    generateView,
    getBatchCapacity: fetchCapacity,
    createDraft,
    uploadView,
  }),
}))

vi.mock('@/composables/useUpload', () => ({
  useUpload: () => ({
    uploading: ref(false),
    uploadFile,
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => (
      params ? `${key}:${JSON.stringify(params)}` : key
    ),
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error,
    success: vi.fn(),
    warning: vi.fn(),
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

const passthroughStub = defineComponent({
  template: '<div><slot /></div>',
})

describe('CharacterReferenceWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeItems.splice(0, storeItems.length, {
      id: 'character-1',
      name: 'Alice',
      description: null,
      status: 'draft',
      task_id: null,
      source_object_key: 'source.png',
      sheet_object_key: null,
      preview_url: null,
      prompt_profile: null,
      default_prompts: {
        face_front: '正脸默认提示词',
        body_front: '正面默认提示词',
        body_side: '侧面默认提示词',
        body_back: '背面默认提示词',
      },
      views: [
        { type: 'face_front', status: 'ready', preview_url: 'front.png' },
        { type: 'body_front', status: 'ready', preview_url: 'body.png' },
      ],
    })
    refresh.mockResolvedValue(undefined)
    generateView.mockResolvedValue(undefined)
    uploadFile.mockResolvedValue('web_uploads/123/front.png')
    uploadView.mockResolvedValue(undefined)
    fetchCapacity.mockResolvedValue({ limit: 3, active: 1, available: 2 })
    createDraft.mockResolvedValue({
      id: 'character-2',
      default_prompts: {
        face_front: '女性正脸默认提示词',
        body_front: '女性正面默认提示词',
        body_side: '女性侧面默认提示词',
        body_back: '女性背面默认提示词',
      },
    })
  })

  it('shows female trait groups and hides them for male characters', async () => {
    const wrapper = mount(CharacterReferenceWorkbench, {
      global: {
        stubs: {
          AButton: ButtonStub,
          AInput: passthroughStub,
          ATextarea: passthroughStub,
          ARadioGroup: passthroughStub,
          ARadioButton: passthroughStub,
          AUpload: passthroughStub,
        },
      },
    })
    expect(wrapper.find('[data-testid="female-options"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="male-note"]').exists()).toBe(false)

    ;(wrapper.vm as any).selectGender('male')
    await nextTick()

    expect(wrapper.find('[data-testid="female-options"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="male-note"]').exists()).toBe(true)
  })

  it('submits selected tags and hydrates prompts from the backend response', async () => {
    const wrapper = mount(CharacterReferenceWorkbench, {
      global: {
        stubs: {
          AButton: ButtonStub,
          AInput: passthroughStub,
          ATextarea: passthroughStub,
          ARadioGroup: passthroughStub,
          ARadioButton: passthroughStub,
          AUpload: passthroughStub,
        },
      },
    })
    ;(wrapper.vm as any).name = 'Alice'
    ;(wrapper.vm as any).description = 'adult woman'
    ;(wrapper.vm as any).sourceKey = 'web_uploads/123/source.png'
    ;(wrapper.vm as any).selectFemaleTag('breast_size', 'large')
    ;(wrapper.vm as any).selectFemaleTag('pubic_hair', 'full')
    ;(wrapper.vm as any).selectFemaleTag('skin_tone', 'asian_tan')

    await (wrapper.vm as any).createDraft()

    expect(createDraft).toHaveBeenCalledWith(expect.objectContaining({
      prompt_profile: {
        gender: 'female',
        breast_size: 'large',
        pubic_hair: 'full',
        skin_tone: 'asian_tan',
      },
    }))
    expect((wrapper.vm as any).prompts.body_front).toBe('女性正面默认提示词')
  })

  it('requires a character description before creating a draft', async () => {
    const wrapper = mount(CharacterReferenceWorkbench, {
      global: {
        stubs: {
          AButton: ButtonStub,
          AInput: passthroughStub,
          ATextarea: passthroughStub,
          ARadioGroup: passthroughStub,
          ARadioButton: passthroughStub,
          AUpload: passthroughStub,
        },
      },
    })
    ;(wrapper.vm as any).name = 'Alice'
    ;(wrapper.vm as any).sourceKey = 'web_uploads/123/source.png'
    ;(wrapper.vm as any).description = '   '

    await (wrapper.vm as any).createDraft()

    expect(createDraft).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledWith('characters.description_required')
  })

  it('uploads the active view directly without submitting a generation task', async () => {
    const wrapper = mount(CharacterReferenceWorkbench, {
      global: {
        stubs: {
          AButton: ButtonStub,
          AInput: passthroughStub,
          ATextarea: passthroughStub,
          ARadioGroup: passthroughStub,
          ARadioButton: passthroughStub,
          AUpload: passthroughStub,
        },
      },
    })
    ;(wrapper.vm as any).draftId = 'character-1'
    for (const [viewType, prompt] of Object.entries(storeItems[0].default_prompts)) {
      ;(wrapper.vm as any).prompts[viewType] = prompt
    }
    await nextTick()

    const file = new File(['front'], 'front.png', { type: 'image/png' })
    await (wrapper.vm as any).beforeViewUpload(file)

    expect(uploadFile).toHaveBeenCalledWith(file, {
      maxSizeBytes: 20 * 1024 * 1024,
      maxSizeLabel: '20MB',
    })
    expect(uploadView).toHaveBeenCalledWith(
      'character-1',
      'face_front',
      'web_uploads/123/front.png',
    )
    expect(generateView).not.toHaveBeenCalled()
  })

  it('submits every missing view through the live concurrency capacity', async () => {
    const wrapper = mount(CharacterReferenceWorkbench, {
      global: {
        stubs: {
          AButton: ButtonStub,
          AInput: passthroughStub,
          ATextarea: passthroughStub,
          ARadioGroup: passthroughStub,
          ARadioButton: passthroughStub,
          AUpload: passthroughStub,
        },
      },
    })
    await flushPromises()
    ;(wrapper.vm as any).draftId = 'character-1'
    for (const [viewType, prompt] of Object.entries(storeItems[0].default_prompts)) {
      ;(wrapper.vm as any).prompts[viewType] = prompt
    }
    await nextTick()

    await wrapper.get('[data-testid="generate-missing-views"]').trigger('click')
    await flushPromises()

    expect(fetchCapacity).toHaveBeenCalledOnce()
    expect(generateView).toHaveBeenCalledTimes(2)
    expect(generateView.mock.calls.map(call => call[1])).toEqual([
      'body_side',
      'body_back',
    ])
    expect(generateView.mock.calls.every(call => call.at(-1) === false)).toBe(true)
  })
})
