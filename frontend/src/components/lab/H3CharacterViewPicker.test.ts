// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import H3CharacterViewPicker from './H3CharacterViewPicker.vue'

const store = vi.hoisted(() => ({
  loading: false,
  refresh: vi.fn(),
  items: [{
    id: 'character-1',
    name: 'Ari',
    status: 'ready',
    moderation_status: 'active',
    preview_url: 'https://cdn/sheet.png',
    adult_confirmed: true,
    usage_rights_confirmed: true,
    views: [{
      type: 'face_front',
      label: 'Front Face',
      status: 'ready',
      object_key: 'character/face.png',
      preview_url: 'https://cdn/face.png',
    }, {
      type: 'body_front_clothed',
      label: 'Clothed Front Body',
      status: 'ready',
      object_key: 'character/body.png',
      preview_url: 'https://cdn/body.png',
    }, {
      type: 'custom_1',
      label: 'Unavailable Detail',
      status: 'pending',
      object_key: null,
      preview_url: null,
    }],
  }],
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => store,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

describe('H3CharacterViewPicker', () => {
  it('emits ordered typed private character view references without the mosaic', async () => {
    const wrapper = mount(H3CharacterViewPicker, {
      props: { references: [], maxItems: 4 },
      global: {
        stubs: {
          'a-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
          'a-modal': { template: '<div><slot /></div>' },
          'a-spin': true,
        },
      },
    })

    expect(wrapper.find('[data-testid="select-character-sheet-character-1"]').exists()).toBe(false)

    await wrapper.get('[data-testid="select-character-view-character-1-face_front"]').trigger('click')
    await wrapper.get('[data-testid="select-character-view-character-1-body_front_clothed"]').trigger('click')

    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({
      key: 'character:character-1:face_front',
      referenceRef: {
        source: 'private_character_view',
        character_id: 'character-1',
        view_type: 'face_front',
      },
    })
    expect(wrapper.emitted('select')?.[1]?.[0]).toMatchObject({
      key: 'character:character-1:body_front_clothed',
      referenceRef: {
        source: 'private_character_view',
        character_id: 'character-1',
        view_type: 'body_front_clothed',
      },
    })
    expect(wrapper.find('[data-testid="select-character-view-character-1-custom_1"]').exists()).toBe(false)
  })

  it('does not emit when the unified four-reference tray is full', async () => {
    const wrapper = mount(H3CharacterViewPicker, {
      props: {
        references: Array.from({ length: 4 }, (_, index) => ({
          key: `upload-${index}`,
          preview: `https://cdn/upload-${index}.png`,
          name: `Upload ${index}`,
        })),
        maxItems: 4,
      },
      global: {
        stubs: {
          'a-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
          'a-modal': { template: '<div><slot /></div>' },
          'a-spin': true,
        },
      },
    })

    await wrapper.get('[data-testid="select-character-view-character-1-face_front"]').trigger('click')
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})
