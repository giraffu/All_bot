// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}))

vi.mock('../api/client', () => ({ api: apiMocks }))

import PromptOptimizerConfigManager from './PromptOptimizerConfigManager.vue'

const PassThrough = defineComponent({ template: '<div><slot /></div>' })

describe('PromptOptimizerConfigManager', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
  })

  it('shows that the effective H3 config comes from the built-in default', async () => {
    apiMocks.get.mockResolvedValue({
      data: [{
        scene_key: 'minimax_h3',
        display_name: '高级图生视频pro',
        description: 'MiniMax H3',
        system_template: 'system',
        user_template: 'user',
        revision: 0,
        content_hash: 'abcdef1234567890',
        template_ref: 'minimax_h3_10eros_naughtytimes@3',
        config_source: 'built-in',
        compatibility_status: 'current',
        fallback_reason: 'no_saved_config',
        stored_revision: null,
      }],
    })

    const wrapper = mount(PromptOptimizerConfigManager, {
      global: {
        stubs: {
          'a-alert': { props: ['message'], template: '<div class="alert">{{ message }}</div>' },
          'a-tabs': PassThrough,
          'a-tab-pane': PassThrough,
          'a-form': PassThrough,
          'a-form-item': PassThrough,
          'a-input': true,
          'a-textarea': true,
          'a-button': PassThrough,
          'a-tag': PassThrough,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('内置默认')
    expect(wrapper.text()).toContain('尚未保存数据库配置')
    expect(wrapper.text()).toContain('minimax_h3_10eros_naughtytimes@3')
  })

  it('warns when an incompatible saved config has fallen back', async () => {
    apiMocks.get.mockResolvedValue({
      data: [{
        scene_key: 'minimax_h3',
        display_name: '高级图生视频pro',
        description: 'MiniMax H3',
        system_template: 'effective system',
        user_template: 'effective user',
        revision: 0,
        content_hash: 'abcdef1234567890',
        template_ref: 'minimax_h3_10eros_naughtytimes@3',
        config_source: 'built-in',
        compatibility_status: 'fallback',
        fallback_reason: 'incompatible_saved_config',
        stored_revision: 7,
      }],
    })

    const wrapper = mount(PromptOptimizerConfigManager, {
      global: {
        stubs: {
          'a-alert': { props: ['message'], template: '<div class="alert">{{ message }}</div>' },
          'a-tabs': PassThrough,
          'a-tab-pane': PassThrough,
          'a-form': PassThrough,
          'a-form-item': PassThrough,
          'a-input': true,
          'a-textarea': true,
          'a-button': PassThrough,
          'a-tag': PassThrough,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('历史 revision 7 与当前模板契约不兼容')
    expect(wrapper.text()).toContain('当前新任务使用内置默认配置')
  })
})
