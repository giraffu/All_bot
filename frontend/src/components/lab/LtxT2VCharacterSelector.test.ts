// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LtxT2VCharacterSelector from './LtxT2VCharacterSelector.vue'

const refresh = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: { index: number }) => params?.index ? `${key}:${params.index}` : key,
  }),
}))

vi.mock('@/stores/characters', () => ({
  useCharactersStore: () => ({
    loading: false,
    refresh,
    readyItems: [
      { id: 'wang', name: '王', description: '成年女性，黑色短发。' },
      { id: 'man', name: '男角色', description: '成年男性，棕色短发。' },
    ],
  }),
}))

vi.mock('@/api/referenceAssets', () => ({
  fetchOfficialCharacters: vi.fn().mockResolvedValue([
    { id: 'official-a', source: 'official', name: '官方角色', description: '官方角色描述' },
  ]),
  fetchOfficialEnvironments: vi.fn().mockResolvedValue([
    { id: 'room-a', source: 'official', name: '官方卧室', description: '暖色卧室' },
  ]),
}))

describe('LtxT2VCharacterSelector', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = { enable_ltx_t2v_msr: true }
  })

  it('shows two ordered character labels without a separate LoRA control', () => {
    const wrapper = mount(LtxT2VCharacterSelector, {
      props: {
        modelValue: ['wang', 'man'],
      },
      global: {
        stubs: {
          'a-select': { template: '<div><slot /></div>' },
          'a-select-option': { template: '<div><slot /></div>' },
          'a-select-opt-group': { template: '<div><slot /></div>' },
          'a-switch': true,
          'a-radio-group': { template: '<div><slot /></div>' },
          'a-radio-button': { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('characters.msr_image_label:1')
    expect(wrapper.text()).toContain('characters.msr_image_label:2')
    expect(wrapper.text()).toContain('王')
    expect(wrapper.text()).toContain('男角色')
    expect(wrapper.find('[data-testid="sulphur-slider"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('characters.msr_hint')
  })
})
