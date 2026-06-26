// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchQqccBotConfig: vi.fn(),
  updateQqccBotConfig: vi.fn(),
}))

const antMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

vi.mock('ant-design-vue', () => ({
  message: {
    error: antMocks.error,
    success: antMocks.success,
  },
}))

import QqccBotSettings from './QqccBotSettings.vue'

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  props: ['loading', 'type'],
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const SwitchStub = defineComponent({
  name: 'SwitchStub',
  props: ['checked'],
  emits: ['update:checked'],
  template:
    '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" />',
})

const CheckboxStub = defineComponent({
  name: 'CheckboxStub',
  props: ['checked'],
  emits: ['update:checked'],
  template:
    '<label><input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" /><slot /></label>',
})

const TextareaStub = defineComponent({
  name: 'TextareaStub',
  props: ['value', 'rows', 'placeholder'],
  emits: ['update:value'],
  template:
    '<textarea :value="value" :rows="rows" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
})

const passthroughStub = (name: string) =>
  defineComponent({
    name,
    template: '<div><slot /></div>',
  })

const mountSettings = () =>
  mount(QqccBotSettings, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-switch': SwitchStub,
        'a-checkbox': CheckboxStub,
        'a-textarea': TextareaStub,
        'a-spin': passthroughStub('SpinStub'),
        'a-form-item': passthroughStub('FormItemStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SaveOutlined: passthroughStub('SaveOutlinedStub'),
      },
    },
  })

describe('QqccBotSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchQqccBotConfig.mockResolvedValue({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-06-26T12:00:00',
      config: {
        global_enabled: true,
        main_buttons: {
          quick_undress: true,
          photo_edit: true,
          video_edit: false,
          main_bot_link: true,
        },
        prompts: {
          undress: 'old prompt',
        },
      },
    })
    apiMocks.updateQqccBotConfig.mockImplementation(payload =>
      Promise.resolve({
        key: 'qqcc_lazy_bot_config:v1',
        updated_at: '2026-06-26T12:01:00',
        config: payload,
      })
    )
  })

  it('loads the config and renders the settings tab content', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    expect(apiMocks.fetchQqccBotConfig).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('懒人Bot配置')
    expect(wrapper.text()).toContain('状态：开启')
    expect(wrapper.text()).toContain('AI动图场景')
  })

  it('saves switch and prompt changes in the payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="global-enabled"]').setValue(false)
    await wrapper.findAll('textarea')[0].setValue('new prompt')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).toHaveBeenCalledOnce()
    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.global_enabled).toBe(false)
    expect(payload.prompts.undress).toBe('new prompt')
    expect(payload.main_buttons.video_edit).toBe(false)
    expect(antMocks.success).toHaveBeenCalledWith('懒人Bot配置已保存')
  })
})
