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
    adult_confirmed: true,
    usage_rights_confirmed: true,
    views: [{
      type: 'face_front',
      label: 'Front Face',
      status: 'ready',
      preview_url: 'https://cdn/face.png',
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
  it('emits a typed private character view reference', async () => {
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

    await wrapper.get('[data-testid="select-character-view-character-1-face_front"]').trigger('click')

    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({
      key: 'character:character-1:face_front',
      referenceRef: {
        source: 'private_character_view',
        character_id: 'character-1',
        view_type: 'face_front',
      },
    })
  })
})
