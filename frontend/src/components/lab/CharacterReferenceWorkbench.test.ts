// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CharacterReferenceWorkbench from './CharacterReferenceWorkbench.vue'

const {
  fetchCapacity,
  generateView,
  refresh,
  storeItems,
} = vi.hoisted(() => ({
  fetchCapacity: vi.fn(),
  generateView: vi.fn(),
  refresh: vi.fn(),
  storeItems: [] as any[],
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => reactive({
    items: storeItems,
    refresh,
    generateView,
    getBatchCapacity: fetchCapacity,
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
    error: vi.fn(),
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
      views: [
        { type: 'face_front', status: 'ready', preview_url: 'front.png' },
        { type: 'face_side', status: 'ready', preview_url: 'side.png' },
        { type: 'face_three_quarter', status: 'ready', preview_url: 'three.png' },
        { type: 'body_front', status: 'ready', preview_url: 'body.png' },
      ],
    })
    refresh.mockResolvedValue(undefined)
    generateView.mockResolvedValue(undefined)
    fetchCapacity.mockResolvedValue({ limit: 3, active: 1, available: 2 })
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
