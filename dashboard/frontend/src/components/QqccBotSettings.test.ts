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

vi.mock('ant-design-vue', () => ({
  message: {
    error: antMocks.error,
    success: antMocks.success,
  },
}))

vi.mock('ant-design-vue/es/message', () => ({
  default: {
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

const ModalStub = defineComponent({
  name: 'ModalStub',
  props: ['open', 'visible', 'title'],
  emits: ['update:open', 'update:visible', 'cancel'],
  template:
    '<div v-if="open || visible" data-testid="scene-model-modal"><h4>{{ title }}</h4><slot /><slot name="footer" /></div>',
})

const passthroughStub = (name: string) =>
  defineComponent({
    name,
    template: '<div><slot /></div>',
  })

const mountSettings = (props = {}) =>
  mount(QqccBotSettings, {
    props: {
      fetchConfig: apiMocks.fetchQqccBotConfig,
      updateConfig: apiMocks.updateQqccBotConfig,
      ...props,
    },
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-switch': SwitchStub,
        'a-checkbox': CheckboxStub,
        'a-input': InputStub,
        'a-textarea': TextareaStub,
        'a-select': SelectStub,
        'a-select-option': SelectOptionStub,
        'a-modal': ModalStub,
        'a-spin': passthroughStub('SpinStub'),
        'a-form': passthroughStub('FormStub'),
        'a-form-item': passthroughStub('FormItemStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SaveOutlined: passthroughStub('SaveOutlinedStub'),
        DeleteOutlined: passthroughStub('DeleteOutlinedStub'),
        PlusOutlined: passthroughStub('PlusOutlinedStub'),
        SettingOutlined: passthroughStub('SettingOutlinedStub'),
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
        scene_preset_version: 1,
        global_enabled: true,
        main_buttons: {
          quick_undress: true,
          quick_faceswap: true,
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
            engine: 'image_to_video',
            lora_name: 'BreastGrow',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [
          {
            id: 'quick_masturbation',
            name: '快速自慰',
            prompt: 'preset masturbation prompt',
            engine: 'free_edit',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
          {
            id: 'quick_undress',
            name: '快速脱衣',
            prompt: 'preset undress prompt',
            engine: 'free_edit',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
          {
            id: 'soft_light',
            name: '柔光写真',
            prompt: 'soft light prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
        ],
      },
      options: {
        video_engines: [
          { value: 'image_to_video', supports_lora: true },
          { value: 'wan22_video_v2', supports_lora: false },
        ],
        draw_engines: [
          { value: 'free_edit', supports_lora: true },
          { value: 'free_edit_v2', supports_lora: false },
        ],
        video_lora_models: [
          { value: '', label: '无' },
          { value: 'BreastGrow', label: '巨乳膨胀' },
        ],
        image_lora_models: [
          { value: '', label: '无' },
          { value: 'qwen/YARN_1.0.safetensors', label: '逼真' },
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
    expect(wrapper.text()).toContain('快速换脸')
    expect(wrapper.text()).toContain('修仙市集')
    expect(wrapper.text()).toContain('AI动图场景')
    expect(wrapper.text()).toContain('AI绘图场景')
    expect(wrapper.text()).not.toContain('懒人P图')
    expect(wrapper.text()).not.toContain('脱衣方式')
    expect((wrapper.get('[data-testid="video-scene-name-0"]').element as HTMLInputElement).value).toBe('亲吻')
    expect((wrapper.get('[data-testid="draw-scene-name-0"]').element as HTMLInputElement).value).toBe('快速自慰')
    expect((wrapper.get('[data-testid="draw-scene-name-1"]').element as HTMLInputElement).value).toBe('快速脱衣')
    expect((wrapper.get('[data-testid="draw-scene-name-2"]').element as HTMLInputElement).value).toBe('柔光写真')
    expect(wrapper.find('[data-testid="non-video-prompt-undress"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="non-video-prompt-masturbation"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="non-video-prompt-face_swap"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('画质与时长')
  })

  it('saves switch, prompt, dynamic video scene, and draw scene changes in the payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="global-enabled"]').setValue(false)
    await wrapper.get('[data-testid="video-scene-name-0"]').setValue('贴贴')
    await wrapper.get('[data-testid="video-scene-prompt-0"]').setValue('new scene prompt')
    await wrapper.get('[data-testid="video-scene-duration-0"]').setValue('10s')
    await wrapper.get('[data-testid="draw-scene-name-2"]').setValue('柔光大片')
    await wrapper.get('[data-testid="draw-scene-prompt-2"]').setValue('new draw prompt')
    await wrapper.get('[data-testid="non-video-prompt-face_swap"]').setValue('new face prompt')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).toHaveBeenCalledOnce()
    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.scene_preset_version).toBe(1)
    expect(JSON.stringify(payload)).not.toContain('prompt_key')
    expect(payload.global_enabled).toBe(false)
    expect(payload.prompts.undress).toBe('old prompt')
    expect(payload.prompts.face_swap).toBe('new face prompt')
    expect(payload.main_buttons.quick_faceswap).toBe(true)
    expect(payload.main_buttons.quick_undress).toBe(false)
    expect(payload.main_buttons.photo_edit).toBe(false)
    expect(payload.main_buttons.video_edit).toBe(false)
    expect(payload.main_buttons.market).toBe(true)
    expect(payload.video_scenes).toEqual([
      {
        id: 'kiss',
        name: '贴贴',
        prompt: 'new scene prompt',
        duration: '10s',
        engine: 'image_to_video',
        lora_name: 'BreastGrow',
        end_frame_draw_scene_id: '',
      },
    ])
    expect(payload.draw_scenes).toEqual([
      {
        id: 'quick_masturbation',
        name: '快速自慰',
        prompt: 'preset masturbation prompt',
        engine: 'free_edit',
        lora_name: '',
        postprocess_draw_scene_id: '',
      },
      {
        id: 'quick_undress',
        name: '快速脱衣',
        prompt: 'preset undress prompt',
        engine: 'free_edit',
        lora_name: '',
        postprocess_draw_scene_id: '',
      },
      {
        id: 'soft_light',
        name: '柔光大片',
        prompt: 'new draw prompt',
        engine: 'free_edit_v2',
        lora_name: '',
        postprocess_draw_scene_id: '',
      },
    ])
    expect(antMocks.success).toHaveBeenCalledWith('懒人Bot配置已保存')
  })

  it('uses injected config API handlers when provided', async () => {
    const fetchConfig = vi.fn().mockResolvedValue({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: null,
      config: {
        global_enabled: true,
        video_scenes: [
          {
            id: 'custom',
            name: '自定义动图',
            prompt: 'custom prompt',
            duration: '5s',
            engine: 'image_to_video',
            lora_name: '',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [],
      },
    })
    const updateConfig = vi.fn(payload =>
      Promise.resolve({
        key: 'qqcc_lazy_bot_config:v1',
        updated_at: null,
        config: payload,
      })
    )

    const wrapper = mountSettings({ fetchConfig, updateConfig })
    await flushPromises()

    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.fetchQqccBotConfig).not.toHaveBeenCalled()
    expect(fetchConfig).toHaveBeenCalledOnce()
    expect(updateConfig).toHaveBeenCalledOnce()
  })

  it('does not synthesize AI drawing preset scenes when draw scenes are absent', async () => {
    const fetchConfig = vi.fn().mockResolvedValue({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: null,
      config: {
        global_enabled: true,
        video_scenes: [
          {
            id: 'custom',
            name: '自定义动图',
            prompt: 'custom prompt',
            duration: '5s',
            engine: 'image_to_video',
            lora_name: '',
            end_frame_draw_scene_id: '',
          },
        ],
      },
    })
    const updateConfig = vi.fn(payload =>
      Promise.resolve({
        key: 'qqcc_lazy_bot_config:v1',
        updated_at: null,
        config: payload,
      })
    )

    const wrapper = mountSettings({ fetchConfig, updateConfig })
    await flushPromises()

    expect(wrapper.find('[data-testid="draw-scene-name-0"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无场景')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = updateConfig.mock.calls[0][0]
    expect(payload.scene_preset_version).toBe(1)
    expect(payload.draw_scenes).toEqual([])
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
    expect(payload.video_scenes[0].engine).toBe('image_to_video')
    expect(payload.video_scenes[0].lora_name).toBe('')
    expect(payload.video_scenes[0].end_frame_draw_scene_id).toBe('')
  })

  it('adds and removes dynamic draw scenes before saving', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-draw-scene"]').trigger('click')
    await wrapper.get('[data-testid="draw-scene-name-3"]').setValue('赛博风')
    await wrapper.get('[data-testid="draw-scene-prompt-3"]').setValue('cyber style')
    await wrapper.get('[data-testid="remove-draw-scene-2"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes).toHaveLength(3)
    expect(payload.draw_scenes[0].name).toBe('快速自慰')
    expect(payload.draw_scenes[1].name).toBe('快速脱衣')
    expect(payload.draw_scenes[2].name).toBe('赛博风')
    expect(payload.draw_scenes[2].prompt).toBe('cyber style')
    expect(payload.draw_scenes[2].engine).toBe('free_edit_v2')
    expect(payload.draw_scenes[2].lora_name).toBe('')
    expect(payload.draw_scenes[2].postprocess_draw_scene_id).toBe('')
  })

  it('configures a video scene model and clears lora when v2 is selected', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('模型与首尾帧配置')
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('wan22_video_v2')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes[0].engine).toBe('wan22_video_v2')
    expect(payload.video_scenes[0].lora_name).toBe('')
  })

  it('configures a video scene end-frame draw source in the save payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect(wrapper.find('[data-testid="scene-end-frame-select"]').exists()).toBe(true)
    await wrapper.get('[data-testid="scene-end-frame-select"]').setValue('soft_light')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes[0].end_frame_draw_scene_id).toBe('soft_light')
  })

  it('shows postprocess source instead of end-frame source on the draw scene model dialog', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-0"]').trigger('click')

    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('模型与后处理配置')
    expect(wrapper.find('[data-testid="scene-end-frame-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="scene-postprocess-select"]').exists()).toBe(true)
  })

  it('clears a video scene end-frame source when the referenced draw scene is removed', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-end-frame-select"]').setValue('soft_light')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="remove-draw-scene-2"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes[0].end_frame_draw_scene_id).toBe('')
  })

  it('configures a draw scene postprocess source in the save payload', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-06-26T12:00:00',
      config: {
        video_scenes: [
          {
            id: 'kiss',
            name: '亲吻',
            prompt: 'kissing prompt',
            duration: '8s',
            engine: 'image_to_video',
            lora_name: '',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [
          {
            id: 'soft_light',
            name: '柔光写真',
            prompt: 'soft light prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
          {
            id: 'anime_finish',
            name: '动漫后期',
            prompt: 'anime finish prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-0"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-postprocess-select"]').text()).toContain('动漫后期')
    await wrapper.get('[data-testid="scene-postprocess-select"]').setValue('anime_finish')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    const softLightScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light')!
    const animeScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'anime_finish')!
    expect(softLightScene.postprocess_draw_scene_id).toBe('anime_finish')
    expect(animeScene.postprocess_draw_scene_id).toBe('')
  })

  it('filters postprocess choices that would create a draw scene cycle', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-06-26T12:00:00',
      config: {
        video_scenes: [
          {
            id: 'kiss',
            name: '亲吻',
            prompt: 'kissing prompt',
            duration: '8s',
            engine: 'image_to_video',
            lora_name: '',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [
          {
            id: 'base_draw',
            name: '基础绘图',
            prompt: 'base draw prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
          {
            id: 'finish_draw',
            name: '后期绘图',
            prompt: 'finish draw prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: 'base_draw',
          },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-0"]').trigger('click')
    const optionValues = wrapper
      .get('[data-testid="scene-postprocess-select"]')
      .findAll('option')
      .map((option) => (option.element as HTMLOptionElement).value)

    expect(optionValues).toContain('')
    expect(optionValues).not.toContain('base_draw')
    expect(optionValues).not.toContain('finish_draw')
  })

  it('clears a draw scene postprocess source when the referenced draw scene is removed', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-06-26T12:00:00',
      config: {
        video_scenes: [
          {
            id: 'kiss',
            name: '亲吻',
            prompt: 'kissing prompt',
            duration: '8s',
            engine: 'image_to_video',
            lora_name: '',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [
          {
            id: 'soft_light',
            name: '柔光写真',
            prompt: 'soft light prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: 'anime_finish',
          },
          {
            id: 'anime_finish',
            name: '动漫后期',
            prompt: 'anime finish prompt',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
          },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="remove-draw-scene-1"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    const softLightScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light')!
    expect(softLightScene.postprocess_draw_scene_id).toBe('')
  })

  it('configures a draw scene to use legacy free edit with a lora model', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-2"]').trigger('click')
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('free_edit')
    await wrapper.get('[data-testid="scene-lora-select"]').setValue('qwen/YARN_1.0.safetensors')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    const softLightScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light')!
    expect(softLightScene.engine).toBe('free_edit')
    expect(softLightScene.lora_name).toBe('qwen/YARN_1.0.safetensors')
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

    await wrapper.get('[data-testid="draw-scene-prompt-2"]').setValue('')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).not.toHaveBeenCalled()
    expect(antMocks.error).toHaveBeenCalledWith('请完善AI绘图场景的按钮名称和提示词')
  })
})
