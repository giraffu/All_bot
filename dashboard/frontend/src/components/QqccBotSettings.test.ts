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

const InputStub = defineComponent({
  name: 'InputStub',
  props: ['value'],
  emits: ['update:value'],
  template:
    '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
})

const TextareaStub = defineComponent({
  name: 'TextareaStub',
  props: ['value', 'rows', 'placeholder'],
  emits: ['update:value'],
  template:
    '<textarea :value="value" :rows="rows" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
})

const SelectStub = defineComponent({
  name: 'SelectStub',
  props: ['value'],
  emits: ['update:value', 'change'],
  template:
    '<select :value="value" @change="$emit(\'update:value\', $event.target.value); $emit(\'change\', $event.target.value)"><slot /></select>',
})

const SelectOptionStub = defineComponent({
  name: 'SelectOptionStub',
  props: ['value'],
  template: '<option :value="value"><slot /></option>',
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
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-select': SelectStub,
        'a-select-option': SelectOptionStub,
        'a-spin': passthroughStub('SpinStub'),
        'a-form-item': passthroughStub('FormItemStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SaveOutlined: passthroughStub('SaveOutlinedStub'),
        DeleteOutlined: passthroughStub('DeleteOutlinedStub'),
        PlusOutlined: passthroughStub('PlusOutlinedStub'),
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
          ai_draw: true,
          video_edit: false,
          market: true,
          main_bot_link: true,
        },
        prompts: {
          undress: 'old prompt',
        },
        video_scenes: [
          {
            id: 'kiss',
            name: '亲吻',
            prompt: 'kissing prompt',
            duration: '8s',
          },
        ],
        draw_scenes: [
          {
            id: 'soft_light',
            name: '柔光写真',
            prompt: 'soft light prompt',
          },
        ],
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
    expect(wrapper.text()).toContain('修仙市集')
    expect(wrapper.text()).toContain('AI动图场景')
    expect(wrapper.text()).toContain('AI绘图场景')
    expect((wrapper.get('[data-testid="video-scene-name-0"]').element as HTMLInputElement).value).toBe('亲吻')
    expect((wrapper.get('[data-testid="draw-scene-name-0"]').element as HTMLInputElement).value).toBe('柔光写真')
    expect(wrapper.text()).not.toContain('画质与时长')
  })

  it('saves switch, prompt, dynamic video scene, and draw scene changes in the payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="global-enabled"]').setValue(false)
    await wrapper.get('[data-testid="video-scene-name-0"]').setValue('贴贴')
    await wrapper.get('[data-testid="video-scene-prompt-0"]').setValue('new scene prompt')
    await wrapper.get('[data-testid="video-scene-duration-0"]').setValue('10s')
    await wrapper.get('[data-testid="draw-scene-name-0"]').setValue('柔光大片')
    await wrapper.get('[data-testid="draw-scene-prompt-0"]').setValue('new draw prompt')
    await wrapper.get('[data-testid="non-video-prompt-undress"]').setValue('new prompt')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).toHaveBeenCalledOnce()
    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.global_enabled).toBe(false)
    expect(payload.prompts.undress).toBe('new prompt')
    expect(payload.main_buttons.video_edit).toBe(false)
    expect(payload.main_buttons.market).toBe(true)
    expect(payload.video_scenes).toEqual([
      {
        id: 'kiss',
        name: '贴贴',
        prompt: 'new scene prompt',
        duration: '10s',
      },
    ])
    expect(payload.draw_scenes).toEqual([
      {
        id: 'soft_light',
        name: '柔光大片',
        prompt: 'new draw prompt',
      },
    ])
    expect(antMocks.success).toHaveBeenCalledWith('懒人Bot配置已保存')
  })

  it('adds and removes dynamic video scenes before saving', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-video-scene"]').trigger('click')
    await wrapper.get('[data-testid="video-scene-name-1"]').setValue('转身')
    await wrapper.get('[data-testid="video-scene-prompt-1"]').setValue('turn around')
    await wrapper.get('[data-testid="remove-video-scene-0"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes).toHaveLength(1)
    expect(payload.video_scenes[0].name).toBe('转身')
    expect(payload.video_scenes[0].prompt).toBe('turn around')
  })

  it('adds and removes dynamic draw scenes before saving', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-draw-scene"]').trigger('click')
    await wrapper.get('[data-testid="draw-scene-name-1"]').setValue('赛博风')
    await wrapper.get('[data-testid="draw-scene-prompt-1"]').setValue('cyber style')
    await wrapper.get('[data-testid="remove-draw-scene-0"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes).toHaveLength(1)
    expect(payload.draw_scenes[0].name).toBe('赛博风')
    expect(payload.draw_scenes[0].prompt).toBe('cyber style')
  })

  it('blocks saving incomplete dynamic video scenes', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="video-scene-prompt-0"]').setValue('')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).not.toHaveBeenCalled()
    expect(antMocks.error).toHaveBeenCalledWith('请完善AI动图场景的按钮名称和提示词')
  })

  it('blocks saving incomplete dynamic draw scenes', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="draw-scene-prompt-0"]').setValue('')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).not.toHaveBeenCalled()
    expect(antMocks.error).toHaveBeenCalledWith('请完善AI绘图场景的按钮名称和提示词')
  })
})
