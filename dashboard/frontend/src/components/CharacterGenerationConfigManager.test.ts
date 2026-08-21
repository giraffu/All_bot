// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMocks }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn() } }))

import CharacterGenerationConfigManager from './CharacterGenerationConfigManager.vue'

const PassThrough = defineComponent({ template: '<div><slot /></div>' })
const config = {
  view_type: 'face_front',
  display_name: '正脸图',
  index: 1,
  required: true,
  prompt_templates: { neutral: 'neutral', female: 'female {tags}', male: 'male {tags}' },
  tag_groups: ['skin_tone'],
  tag_options: {
    breast_size: { large: 'large', natural: 'natural', flat: 'flat' },
    pubic_hair: { full: 'full', natural: 'natural', none: 'none' },
    skin_tone: { fair: 'fair', asian_yellow: 'yellow', asian_tan: 'tan' },
  },
  revision: 0,
  content_hash: 'abcdef1234567890',
  config_source: 'built-in',
}

describe('CharacterGenerationConfigManager', () => {
  beforeEach(() => {
    apiMocks.get.mockReset().mockResolvedValue({ data: [structuredClone(config)] })
    apiMocks.put.mockReset().mockResolvedValue({ data: { ...structuredClone(config), revision: 1, config_source: 'database' } })
  })

  it('loads per-view names, templates and tag combinations and publishes edits', async () => {
    const wrapper = mount(CharacterGenerationConfigManager, {
      global: {
        stubs: {
          'a-alert': { props: ['message'], template: '<div>{{ message }}</div>' },
          'a-tabs': PassThrough,
          'a-tab-pane': PassThrough,
          'a-form': PassThrough,
          'a-form-item': PassThrough,
          'a-input': true,
          'a-textarea': true,
          'a-button': PassThrough,
          'a-tag': PassThrough,
          'a-checkbox': PassThrough,
          'a-checkbox-group': PassThrough,
          'a-collapse': PassThrough,
          'a-collapse-panel': PassThrough,
        },
      },
    })
    await flushPromises()

    expect((wrapper.vm as any).configs[0].display_name).toBe('正脸图')
    expect((wrapper.vm as any).configs[0].tag_groups).toEqual(['skin_tone'])
    await (wrapper.vm as any).save((wrapper.vm as any).configs[0])

    expect(apiMocks.put).toHaveBeenCalledWith('/api/character-generation/configs/face_front', {
      display_name: '正脸图',
      prompt_templates: config.prompt_templates,
      tag_groups: ['skin_tone'],
      tag_options: config.tag_options,
    })
  })
})
