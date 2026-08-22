// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn() }))
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
    apiMocks.get.mockReset().mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/templates') ? [] : [structuredClone(config)],
    }))
    apiMocks.put.mockReset().mockResolvedValue({ data: { ...structuredClone(config), revision: 1, config_source: 'database' } })
    apiMocks.post.mockReset().mockResolvedValue({ data: {} })
    apiMocks.patch.mockReset().mockResolvedValue({ data: {} })
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
          'a-select': PassThrough,
          'a-select-option': PassThrough,
          'a-input-number': true,
          'a-upload': PassThrough,
          'a-empty': PassThrough,
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

  it('uploads one of multiple body-detail image templates', async () => {
    const wrapper = mount(CharacterGenerationConfigManager, {
      global: { stubs: {
        'a-alert': PassThrough,
        'a-tabs': PassThrough,
        'a-tab-pane': PassThrough,
        'a-form': PassThrough,
        'a-form-item': PassThrough,
        'a-input': true,
        'a-input-number': true,
        'a-select': PassThrough,
        'a-select-option': PassThrough,
        'a-upload': PassThrough,
        'a-button': PassThrough,
        'a-empty': PassThrough,
        'a-tag': PassThrough,
        'a-checkbox': PassThrough,
        'a-checkbox-group': PassThrough,
        'a-collapse': PassThrough,
        'a-collapse-panel': PassThrough,
        'a-textarea': true,
      } },
    })
    await flushPromises()
    ;(wrapper.vm as any).templateForm.view_type = 'genitals_front'
    ;(wrapper.vm as any).templateForm.name = '模板 A'
    ;(wrapper.vm as any).templateForm.gender = 'female'
    ;(wrapper.vm as any).uploadFile = new File(['image'], 'template.png', { type: 'image/png' })

    await (wrapper.vm as any).createTemplate()

    expect(apiMocks.post).toHaveBeenCalledWith(
      '/api/character-generation/configs/templates',
      expect.any(FormData),
    )
    const payload = apiMocks.post.mock.calls[0][1] as FormData
    expect(payload.get('view_type')).toBe('genitals_front')
    expect(payload.get('name')).toBe('模板 A')
  })

  it('saves one template as the automatic default for its body-detail slot', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/templates') ? [{
        id: 'template-old',
        view_type: 'torso_front',
        name: '旧默认胸部模板',
        gender: 'female',
        sort_order: 5,
        status: 'active',
        is_default: true,
        preview_url: 'old-template.png',
      }, {
        id: 'template-1',
        view_type: 'torso_front',
        name: '默认胸部模板',
        gender: 'female',
        sort_order: 10,
        status: 'active',
        is_default: false,
        preview_url: 'template.png',
      }] : [structuredClone(config)],
    }))
    apiMocks.patch.mockResolvedValue({ data: {
      id: 'template-1',
      view_type: 'torso_front',
      name: '默认胸部模板',
      gender: 'female',
      sort_order: 10,
      status: 'active',
      is_default: true,
      preview_url: 'template.png',
    } })
    const wrapper = mount(CharacterGenerationConfigManager, {
      global: { stubs: {
        'a-alert': PassThrough, 'a-tabs': PassThrough, 'a-tab-pane': PassThrough,
        'a-form': PassThrough, 'a-form-item': PassThrough, 'a-input': true,
        'a-input-number': true, 'a-select': PassThrough, 'a-select-option': PassThrough,
        'a-upload': PassThrough, 'a-button': PassThrough, 'a-empty': PassThrough,
        'a-tag': PassThrough, 'a-checkbox': PassThrough, 'a-checkbox-group': PassThrough,
        'a-collapse': PassThrough, 'a-collapse-panel': PassThrough, 'a-textarea': true,
        'a-switch': true,
      } },
    })
    await flushPromises()
    const template = (wrapper.vm as any).templates[1]
    ;(wrapper.vm as any).setDefault(template, true)

    expect((wrapper.vm as any).templates[0].is_default).toBe(false)

    await (wrapper.vm as any).saveTemplate(template)

    expect(apiMocks.patch).toHaveBeenCalledWith(
      '/api/character-generation/configs/templates/template-1',
      expect.objectContaining({ is_default: true }),
    )
  })
})
