// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchQqccBotConfig: vi.fn(),
  updateQqccBotConfig: vi.fn(),
  uploadQqccDemoMedia: vi.fn(),
  generateQqccDemoMedia: vi.fn(),
  getQqccDemoGeneration: vi.fn(),
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
  props: ['disabled', 'loading', 'type'],
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
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

const InputNumberStub = defineComponent({
  name: 'InputNumberStub',
  props: ['value', 'min', 'step', 'precision', 'placeholder'],
  emits: ['update:value'],
  template: '<input type="number" :value="value ?? \'\'" :min="min" :step="step" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value === \'\' ? null : Number($event.target.value))" />',
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

const TabsStub = defineComponent({
  name: 'TabsStub',
  props: ['activeKey'],
  emits: ['update:activeKey'],
  template: `
    <div>
      <div>
        <button type="button" data-testid="scene-tab-control-video" @click="$emit('update:activeKey', 'video')">AI动图</button>
        <button type="button" data-testid="scene-tab-control-ai-video" @click="$emit('update:activeKey', 'ai_video')">AI视频</button>
        <button type="button" data-testid="scene-tab-control-draw" @click="$emit('update:activeKey', 'draw')">AI绘图</button>
        <button type="button" data-testid="scene-tab-control-filter" @click="$emit('update:activeKey', 'filter')">AI滤镜</button>
      </div>
      <slot />
    </div>
  `,
})

const TabPaneStub = defineComponent({
  name: 'TabPaneStub',
  props: ['tab'],
  template: '<div><slot name="tab" /><slot /></div>',
})

const PaginationStub = defineComponent({
  name: 'PaginationStub',
  props: ['current', 'pageSize', 'total'],
  emits: ['update:current', 'change'],
  template: `
    <div>
      <button
        type="button"
        data-testid="pagination-next"
        @click="$emit('update:current', current + 1); $emit('change', current + 1)"
      >下一页</button>
    </div>
  `,
})

const UploadStub = defineComponent({
  name: 'UploadStub',
  props: ['beforeUpload', 'accept', 'showUploadList'],
  template: '<div><slot /></div>',
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
      uploadDemoMedia: apiMocks.uploadQqccDemoMedia,
      generateDemoMedia: apiMocks.generateQqccDemoMedia,
      getDemoGeneration: apiMocks.getQqccDemoGeneration,
      ...props,
    },
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-switch': SwitchStub,
        'a-checkbox': CheckboxStub,
        'a-input': InputStub,
        'a-input-number': InputNumberStub,
        'a-textarea': TextareaStub,
        'a-select': SelectStub,
        'a-select-option': SelectOptionStub,
        'a-modal': ModalStub,
        'a-tabs': TabsStub,
        'a-tab-pane': TabPaneStub,
        'a-pagination': PaginationStub,
        'a-upload': UploadStub,
        'a-spin': passthroughStub('SpinStub'),
        'a-form': passthroughStub('FormStub'),
        'a-form-item': passthroughStub('FormItemStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SaveOutlined: passthroughStub('SaveOutlinedStub'),
        DeleteOutlined: passthroughStub('DeleteOutlinedStub'),
        DownOutlined: passthroughStub('DownOutlinedStub'),
        InfoCircleOutlined: passthroughStub('InfoCircleOutlinedStub'),
        LinkOutlined: passthroughStub('LinkOutlinedStub'),
        PlusOutlined: passthroughStub('PlusOutlinedStub'),
        PlayCircleOutlined: passthroughStub('PlayCircleOutlinedStub'),
        SettingOutlined: passthroughStub('SettingOutlinedStub'),
        UpOutlined: passthroughStub('UpOutlinedStub'),
        UploadOutlined: passthroughStub('UploadOutlinedStub'),
      },
    },
  })

const getButtonByTestId = (wrapper: ReturnType<typeof mountSettings>, testId: string) => {
  const button = wrapper
    .findAllComponents(ButtonStub)
    .find(component => component.attributes('data-testid') === testId)
  if (!button) throw new Error(`Missing button: ${testId}`)
  return button
}

describe('QqccBotSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.uploadQqccDemoMedia.mockResolvedValue({
      media: {
        object_key: 'qqcc/demo/draw/quick_masturbation/input',
        media_type: 'image',
        mime_type: 'image/png',
        file_name: 'before.png',
        telegram_file_ids: {},
      },
      preview_url: 'https://preview.example/before.png',
    })
    apiMocks.generateQqccDemoMedia.mockResolvedValue({
      generation_id: 'task-1',
      status: 'pending',
    })
    apiMocks.getQqccDemoGeneration.mockResolvedValue({
      generation_id: 'task-1',
      status: 'done',
      config_saved: true,
      media: {
        object_key: 'qqcc/demo/draw/quick_masturbation/output',
        media_type: 'image',
        mime_type: 'image/png',
        file_name: 'generated.png',
        telegram_file_ids: {},
      },
      preview_url: 'https://preview.example/generated.png',
    })
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
          ai_filter: true,
          video_edit: false,
          market: true,
          main_bot_link: true,
          private_bot: true,
        },
        prompts: {
          undress: 'old prompt',
        },
        copywriting: {
          ai_draw_scene_start: '已切换到【{butten}】模式，请发送一张图片。',
        },
        video_scenes: [
          {
            id: 'kiss',
            name: '亲吻',
            prompt: 'kissing prompt',
            negative_prompt: 'video negative',
            duration: '8s',
            engine: 'image_to_video',
            aspect_ratio: '9:16',
            lora_name: 'BreastGrow',
            end_frame_draw_scene_id: '',
          },
        ],
        draw_scenes: [
          {
            id: 'quick_masturbation',
            name: '快速自慰',
            prompt: 'preset masturbation prompt',
            negative_prompt: 'masturbation negative',
            engine: 'free_edit',
            lora_name: '',
            postprocess_draw_scene_id: '',
            postprocess_filter_scene_id: '',
            original_face_swap_enabled: false,
          },
          {
            id: 'quick_undress',
            name: '快速脱衣',
            prompt: 'preset undress prompt',
            negative_prompt: '',
            engine: 'free_edit',
            lora_name: '',
            postprocess_draw_scene_id: '',
            postprocess_filter_scene_id: '',
            original_face_swap_enabled: false,
          },
          {
            id: 'soft_light',
            name: '柔光写真',
            prompt: 'soft light prompt',
            negative_prompt: 'soft light negative',
            engine: 'free_edit_v2',
            lora_name: '',
            postprocess_draw_scene_id: '',
            postprocess_filter_scene_id: '',
            original_face_swap_enabled: false,
          },
        ],
        filter_scenes: [
          {
            id: 'real_skin',
            name: '真实质感',
            prompt: 'real skin prompt',
            negative_prompt: 'plastic skin',
            engine: 'free_edit_v2',
            lora_name: '',
            original_face_swap_enabled: false,
          },
        ],
      },
      options: {
        video_engines: [
          { value: 'image_to_video', supports_lora: true },
          { value: 'wan22_video_v2', supports_lora: true },
        ],
        video_aspect_ratios: ['source', '9:16', '16:9', '1:1'],
        video_resolutions: [
          { value: '512p', label: '512p' },
          { value: '720p', label: '720p' },
          { value: '1024p', label: '1024p' },
        ],
        ai_video_resolutions: [{ value: '1280x704', label: '1280×704' }],
        default_video_resolution: '720p',
        default_ai_video_resolution: '1280x704',
        draw_engines: [
          { value: 'free_edit', supports_lora: true },
          { value: 'free_edit_v2', supports_lora: false },
          { value: 'free_edit_v3', supports_lora: false },
        ],
        video_lora_models: [
          { value: 'BreastGrow', label: '巨乳膨胀', default_strength: 0.7 },
          { value: 'BreastInsertion', label: '乳交', default_strength: 0.8 },
          { value: 'Cum', label: '颜射', default_strength: 1 },
          { value: 'Cunilingus', label: '舔阴', default_strength: 0.9 },
          { value: 'Footjob', label: '足交', default_strength: 1.4 },
          { value: 'Insertion', label: '插入优化', default_strength: 1 },
        ],
        image_lora_models: [
          { value: '', label: '无' },
          { value: 'qwen/YARN_1.0.safetensors', label: '逼真' },
        ],
        default_scene_credit_costs: {
          video: 6,
          ai_video: 10,
          draw: 2,
          filter: 2,
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

  it('uploads and previews input demo media on the matching scene row', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const uploads = wrapper.findAllComponents(UploadStub)
    const drawInputUpload = uploads[2]
    expect(drawInputUpload).toBeTruthy()
    const file = new File(['demo'], 'before.png', { type: 'image/png' })

    await drawInputUpload!.props('beforeUpload')(file)
    await flushPromises()

    expect(apiMocks.uploadQqccDemoMedia).toHaveBeenCalledWith(
      'draw',
      'quick_masturbation',
      'input',
      file,
    )
    expect(
      wrapper.get('[data-testid="draw-demo-input-preview-0"]').attributes('src'),
    ).toBe('https://preview.example/before.png')
    expect(
      wrapper.get('[data-testid="draw-demo-input-preview-0"]').attributes('width'),
    ).toBe('60')
    expect(
      wrapper.get('[data-testid="draw-demo-input-preview-0"]').element.closest('.scene-action-cell'),
    ).not.toBeNull()
  })

  it('keeps every concurrent demo upload and generation button in its own loading state', async () => {
    const uploads = [] as Array<(value: { media: Record<string, unknown>; preview_url: string }) => void>
    const generations = [] as Array<(value: Record<string, unknown>) => void>
    apiMocks.uploadQqccDemoMedia.mockImplementation(
      () => new Promise(resolve => uploads.push(resolve)),
    )
    const wrapper = mountSettings()
    await flushPromises()

    const uploadControls = wrapper.findAllComponents(UploadStub)
    const firstUpload = uploadControls[2]!.props('beforeUpload')
    const secondUpload = uploadControls[4]!.props('beforeUpload')
    const file = new File(['demo'], 'before.png', { type: 'image/png' })
    const firstUploadPromise = firstUpload(file)
    const secondUploadPromise = secondUpload(file)
    await flushPromises()

    expect(getButtonByTestId(wrapper, 'upload-draw-demo-input-0').props('loading')).toBe(true)
    expect(getButtonByTestId(wrapper, 'upload-draw-demo-input-1').props('loading')).toBe(true)

    uploads[0]!({ media: { object_key: 'first', media_type: 'image', mime_type: 'image/png', file_name: 'first.png' }, preview_url: 'https://preview.example/first.png' })
    uploads[1]!({ media: { object_key: 'second', media_type: 'image', mime_type: 'image/png', file_name: 'second.png' }, preview_url: 'https://preview.example/second.png' })
    await Promise.all([firstUploadPromise, secondUploadPromise])

    apiMocks.generateQqccDemoMedia.mockImplementation(
      () => new Promise(resolve => generations.push(resolve)),
    )
    await wrapper.get('[data-testid="generate-draw-demo-0"]').trigger('click')
    await wrapper.get('[data-testid="generate-draw-demo-1"]').trigger('click')
    await flushPromises()

    expect(getButtonByTestId(wrapper, 'generate-draw-demo-0').props('loading')).toBe(true)
    expect(getButtonByTestId(wrapper, 'generate-draw-demo-1').props('loading')).toBe(true)

    generations[0]!({ generation_id: 'generation-1', status: 'done', config_saved: true, media: { object_key: 'output-1' }, preview_url: 'https://preview.example/output-1.png' })
    generations[1]!({ generation_id: 'generation-2', status: 'done', config_saved: true, media: { object_key: 'output-2' }, preview_url: 'https://preview.example/output-2.png' })
    await flushPromises()
  })

  it('shows the output returned by an automatically persisted generation', async () => {
    const wrapper = mountSettings()
    await flushPromises()
    const file = new File(['demo'], 'before.png', { type: 'image/png' })
    await wrapper.findAllComponents(UploadStub)[2]!.props('beforeUpload')(file)
    await flushPromises()

    await wrapper.get('[data-testid="generate-draw-demo-0"]').trigger('click')
    await flushPromises()

    expect(apiMocks.generateQqccDemoMedia).toHaveBeenCalledWith(
      'draw',
      expect.objectContaining({
        id: 'quick_masturbation',
        prompt: 'preset masturbation prompt',
        demo_input_media: expect.objectContaining({
          object_key: 'qqcc/demo/draw/quick_masturbation/input',
        }),
      }),
    )
    expect(apiMocks.getQqccDemoGeneration).toHaveBeenCalledWith(
      'draw',
      'quick_masturbation',
      'task-1',
    )
    expect(apiMocks.updateQqccBotConfig).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="draw-demo-output-preview-0"]').attributes('src')).toBe(
      'https://preview.example/generated.png',
    )
    expect(antMocks.success).toHaveBeenCalledWith('输出示范已生成并自动保存')
  })

  it('opens a large modal preview when the generated video is clicked', async () => {
    apiMocks.uploadQqccDemoMedia.mockResolvedValueOnce({
      media: {
        object_key: 'qqcc/demo/video/kiss/output',
        media_type: 'video',
        mime_type: 'video/mp4',
        file_name: 'generated.mp4',
        telegram_file_ids: {},
      },
      preview_url: 'https://preview.example/generated.mp4',
    })
    const wrapper = mountSettings()
    await flushPromises()

    const file = new File(['video'], 'generated.mp4', { type: 'video/mp4' })
    await wrapper.findAllComponents(UploadStub)[1]!.props('beforeUpload')(file)
    await flushPromises()

    await wrapper.get('[data-testid="video-demo-output-preview-0"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="demo-video-modal-player"]').attributes('src')).toBe(
      'https://preview.example/generated.mp4',
    )
    expect(wrapper.get('[data-testid="demo-video-modal"]').text()).toContain('亲吻 · 输出示范')
  })

  it('shows the backend reason when demo media upload is rejected', async () => {
    apiMocks.uploadQqccDemoMedia.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: 'Demo file content does not match its type' },
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    const uploads = wrapper.findAllComponents(UploadStub)
    const drawInputUpload = uploads[2]
    const file = new File(['not-a-png'], 'before.png', { type: 'image/png' })

    await drawInputUpload!.props('beforeUpload')(file)
    await flushPromises()

    expect(antMocks.error).toHaveBeenCalledWith(
      '示范文件上传失败：文件内容与声明格式不一致',
    )
  })

  it('reports a Cloudflare edge rejection instead of an expired session for 403', async () => {
    apiMocks.uploadQqccDemoMedia.mockRejectedValueOnce({
      response: { status: 403 },
    })
    const wrapper = mountSettings()
    await flushPromises()

    const file = new File(['demo'], 'before.png', { type: 'image/png' })
    await wrapper.findAllComponents(UploadStub)[2]!.props('beforeUpload')(file)
    await flushPromises()

    expect(antMocks.error).toHaveBeenCalledWith(
      '示范文件上传失败：Cloudflare 安全规则拦截了上传请求',
    )
  })

  it('explains when the edge returns HTML instead of upload data', async () => {
    apiMocks.uploadQqccDemoMedia.mockResolvedValueOnce('<!doctype html>Access login')
    const wrapper = mountSettings()
    await flushPromises()

    const uploads = wrapper.findAllComponents(UploadStub)
    const drawInputUpload = uploads[2]
    const file = new File(['demo'], 'before.png', { type: 'image/png' })

    await drawInputUpload!.props('beforeUpload')(file)
    await flushPromises()

    expect(antMocks.error).toHaveBeenCalledWith(
      '示范文件上传失败：公网安全层返回了非预期响应',
    )
  })

  it('keeps tenant-scoped demo media when the owner editor reloads config', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_private_bot_config:7',
      updated_at: '2026-07-12T12:00:00',
      config: {
        video_scenes: [],
        filter_scenes: [],
        draw_scenes: [
          {
            id: 'tenant_draw',
            name: '租户绘图',
            prompt: 'tenant prompt',
            engine: 'free_edit_v2',
            demo_input_media: {
              object_key: 'qqcc/private/7/demo/draw/tenant_draw/input',
              media_type: 'image',
              mime_type: 'image/png',
              file_name: 'tenant.png',
              preview_url: 'https://preview.example/tenant.png',
            },
          },
        ],
      },
    })
    const wrapper = mountSettings({
      demoMediaObjectPrefixes: ['qqcc/demo', 'qqcc/private/7/demo'],
    })
    await flushPromises()

    expect(
      wrapper.get('[data-testid="draw-demo-input-preview-0"]').attributes('src'),
    ).toBe('https://preview.example/tenant.png')
  })

  it('uses image demos for drawing and filters but mp4 for video output', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const uploads = wrapper.findAllComponents(UploadStub)
    expect(uploads).toHaveLength(10)
    expect(uploads[0]!.props('accept')).toContain('image/png')
    expect(uploads[1]!.props('accept')).toContain('video/mp4')
    expect(uploads[2]!.props('accept')).toContain('image/png')
    expect(uploads[3]!.props('accept')).toContain('image/png')
    expect(uploads[8]!.props('accept')).toContain('image/png')
    expect(uploads[9]!.props('accept')).toContain('image/png')
  })

  it('loads the config and renders the settings tab content', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    expect(apiMocks.fetchQqccBotConfig).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('懒人Bot配置')
    expect(wrapper.text()).toContain('状态：开启')
    expect(wrapper.text()).toContain('快速换脸')
    expect(wrapper.text()).toContain('AI滤镜')
    expect(wrapper.text()).toContain('修仙市集')
    expect(wrapper.text()).toContain('AI场景配置')
    expect(wrapper.get('[data-testid="scene-tab-video"]').text()).toContain('AI动图')
    expect(wrapper.get('[data-testid="scene-tab-draw"]').text()).toContain('AI绘图')
    expect(wrapper.get('[data-testid="scene-tab-filter"]').text()).toContain('AI滤镜')
    expect(wrapper.text()).not.toContain('懒人P图')
    expect(wrapper.text()).not.toContain('脱衣方式')
    expect((wrapper.get('[data-testid="video-scene-name-0"]').element as HTMLInputElement).value).toBe('亲吻')
    expect((wrapper.get('[data-testid="video-scene-negative-prompt-0"]').element as HTMLTextAreaElement).value).toBe('video negative')
    expect((wrapper.get('[data-testid="draw-scene-name-0"]').element as HTMLInputElement).value).toBe('快速自慰')
    expect((wrapper.get('[data-testid="draw-scene-name-1"]').element as HTMLInputElement).value).toBe('快速脱衣')
    expect((wrapper.get('[data-testid="draw-scene-name-2"]').element as HTMLInputElement).value).toBe('柔光写真')
    expect((wrapper.get('[data-testid="draw-scene-negative-prompt-2"]').element as HTMLTextAreaElement).value).toBe('soft light negative')
    expect((wrapper.get('[data-testid="filter-scene-name-0"]').element as HTMLInputElement).value).toBe('真实质感')
    expect((wrapper.get('[data-testid="filter-scene-negative-prompt-0"]').element as HTMLTextAreaElement).value).toBe('plastic skin')
    expect(wrapper.find('[data-testid="non-video-prompt-undress"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="non-video-prompt-masturbation"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="non-video-prompt-face_swap"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="copywriting-ai_draw_scene_start"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="copywriting-ai_draw_scene_start"]').element as HTMLTextAreaElement).value).toBe(
      '已切换到【{butten}】模式，请发送一张图片。',
    )
    expect(wrapper.get('[data-testid="copywriting-ai_filter_scene_start"]').attributes('placeholder')).toContain(
      '已切换到【{butten}】模式',
    )
    expect(wrapper.find('[data-testid="config-video-scene-0"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="config-video-scene-0"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="config-draw-scene-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="config-filter-scene-0"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('画质与时长')
  })

  it('renders taller prompt editors for every scene kind', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    for (const testId of [
      'video-scene-prompt-0',
      'video-scene-negative-prompt-0',
      'draw-scene-prompt-0',
      'draw-scene-negative-prompt-0',
      'filter-scene-prompt-0',
      'filter-scene-negative-prompt-0',
    ]) {
      expect(wrapper.get(`[data-testid="${testId}"]`).attributes('rows')).toBe('5')
    }
  })

  it('keeps legacy menu layout until columns are selected and saves reordered hidden buttons', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const layoutSelect = wrapper.get('[data-testid="main-menu-buttons-per-row"]')
    expect((layoutSelect.element as HTMLSelectElement).value).toBe('legacy')
    expect(getButtonByTestId(wrapper, 'move-main-menu-button-up-quick_faceswap').props('disabled')).toBe(true)
    expect(getButtonByTestId(wrapper, 'move-main-menu-button-down-quick_faceswap').props('disabled')).toBe(true)

    await layoutSelect.setValue('2')
    await getButtonByTestId(wrapper, 'move-main-menu-button-up-market').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.main_menu_layout).toEqual({
      buttons_per_row: 2,
      button_order: [
        'quick_faceswap',
        'ai_draw',
        'ai_filter',
        'video_edit',
        'market',
        'ai_video',
        'private_bot',
        'main_bot_link',
      ],
    })
    expect(payload.main_buttons.video_edit).toBe(false)
  })

  it('saves switch, prompt, dynamic video scene, and draw scene changes in the payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="global-enabled"]').setValue(false)
    await wrapper.get('[data-testid="main-button-private_bot"]').setValue(false)
    await wrapper.get('[data-testid="video-scene-name-0"]').setValue('贴贴')
    await wrapper.get('[data-testid="video-scene-prompt-0"]').setValue('new scene prompt')
    await wrapper.get('[data-testid="video-scene-negative-prompt-0"]').setValue('  video bad hands  ')
    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-config-duration"]').setValue('10s')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="draw-scene-name-2"]').setValue('柔光大片')
    await wrapper.get('[data-testid="draw-scene-prompt-2"]').setValue('new draw prompt')
    await wrapper.get('[data-testid="draw-scene-negative-prompt-2"]').setValue('  draw blur  ')
    await wrapper.get('[data-testid="filter-scene-name-0"]').setValue('真实滤镜')
    await wrapper.get('[data-testid="filter-scene-prompt-0"]').setValue('new filter prompt')
    await wrapper.get('[data-testid="filter-scene-negative-prompt-0"]').setValue('  filter blur  ')
    await wrapper.get('[data-testid="non-video-prompt-face_swap"]').setValue('new face prompt')
    await wrapper.get('[data-testid="copywriting-ai_draw_scene_start"]').setValue('请发送【{butten}】的原图。')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).toHaveBeenCalledOnce()
    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.scene_preset_version).toBe(1)
    expect(JSON.stringify(payload)).not.toContain('prompt_key')
    expect(payload.global_enabled).toBe(false)
    expect(payload.prompts.undress).toBe('old prompt')
    expect(payload.prompts.face_swap).toBe('new face prompt')
    expect(payload.copywriting.ai_draw_scene_start).toBe('请发送【{butten}】的原图。')
    expect(payload.main_buttons.quick_faceswap).toBe(true)
    expect(payload.main_buttons.ai_filter).toBe(true)
    expect(payload.main_buttons.quick_undress).toBe(false)
    expect(payload.main_buttons.photo_edit).toBe(false)
    expect(payload.main_buttons.video_edit).toBe(false)
    expect(payload.main_buttons.market).toBe(true)
    expect(payload.main_buttons.private_bot).toBe(false)
    expect(payload.video_scenes).toEqual([
      {
        id: 'kiss',
        name: '贴贴',
        prompt: 'new scene prompt',
        negative_prompt: 'video bad hands',
        duration: '10s',
        resolution: '720p',
        engine: 'image_to_video',
        aspect_ratio: '9:16',
        lora_name: 'BreastGrow',
        lora_strength: 0.7,
        lora_items: [{ name: 'BreastGrow', strength: 0.7 }],
        end_frame_draw_scene_id: '',
        next_scene_id: null,
        credit_cost: null,
      },
    ])
    expect(payload.draw_scenes).toEqual([
      {
        id: 'quick_masturbation',
        name: '快速自慰',
        prompt: 'preset masturbation prompt',
        negative_prompt: 'masturbation negative',
        engine: 'free_edit',
        lora_name: '',
        postprocess_draw_scene_id: '',
        postprocess_filter_scene_id: '',
        original_face_swap_enabled: false,
        credit_cost: null,
      },
      {
        id: 'quick_undress',
        name: '快速脱衣',
        prompt: 'preset undress prompt',
        negative_prompt: '',
        engine: 'free_edit',
        lora_name: '',
        postprocess_draw_scene_id: '',
        postprocess_filter_scene_id: '',
        original_face_swap_enabled: false,
        credit_cost: null,
      },
      {
        id: 'soft_light',
        name: '柔光大片',
        prompt: 'new draw prompt',
        negative_prompt: 'draw blur',
        engine: 'free_edit_v2',
        lora_name: '',
        postprocess_draw_scene_id: '',
        postprocess_filter_scene_id: '',
        original_face_swap_enabled: false,
        credit_cost: null,
      },
    ])
    expect(payload.filter_scenes).toEqual([
      {
        id: 'real_skin',
        name: '真实滤镜',
        prompt: 'new filter prompt',
        negative_prompt: 'filter blur',
        engine: 'free_edit_v2',
        lora_name: '',
        original_face_swap_enabled: false,
        credit_cost: null,
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
    expect((wrapper.get('[data-testid="video-scene-negative-prompt-1"]').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.get('[data-testid="video-scene-name-1"]').setValue('转身')
    await wrapper.get('[data-testid="video-scene-prompt-1"]').setValue('turn around')
    await wrapper.get('[data-testid="video-scene-negative-prompt-1"]').setValue('motion blur')
    await wrapper.get('[data-testid="remove-video-scene-0"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes).toHaveLength(1)
    expect(payload.video_scenes[0].name).toBe('转身')
    expect(payload.video_scenes[0].prompt).toBe('turn around')
    expect(payload.video_scenes[0].negative_prompt).toBe('motion blur')
    expect(payload.video_scenes[0].engine).toBe('image_to_video')
    expect(payload.video_scenes[0].aspect_ratio).toBe('source')
    expect(payload.video_scenes[0].lora_name).toBe('')
    expect(payload.video_scenes[0].end_frame_draw_scene_id).toBe('')
  })

  it('loads legacy scene prices as empty and uses backend defaults for new scenes', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="config-draw-scene-0"]').trigger('click')
    expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="config-filter-scene-0"]').trigger('click')
    expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')

    await wrapper.get('[data-testid="add-video-scene"]').trigger('click')
    await wrapper.get('[data-testid="add-ai-video-scene"]').trigger('click')
    await wrapper.get('[data-testid="add-draw-scene"]').trigger('click')
    await wrapper.get('[data-testid="add-filter-scene"]').trigger('click')

    for (const [testId, expected] of [
      ['config-video-scene-1', '6'],
      ['config-ai-video-scene-0', '10'],
      ['config-draw-scene-3', '2'],
      ['config-filter-scene-1', '2'],
    ]) {
      await wrapper.get(`[data-testid="${testId}"]`).trigger('click')
      expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe(expected)
      await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    }
  })

  it('does not invent a new scene price when options omit defaults', async () => {
    const fetchConfig = vi.fn().mockResolvedValue({
      config: {
        scene_preset_version: 1,
        video_scenes: [],
        ai_video_scenes: [],
        draw_scenes: [],
        filter_scenes: [],
      },
      options: {},
    })
    const wrapper = mountSettings({ fetchConfig })
    await flushPromises()

    await wrapper.get('[data-testid="add-video-scene"]').trigger('click')

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe('')
  })

  it('saves configured and cleared scene credit costs', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-config-credit-cost"]').setValue('7')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="config-draw-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-config-credit-cost"]').setValue('3')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.get('[data-testid="config-filter-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-config-credit-cost"]').setValue('')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes[0].credit_cost).toBe(7)
    expect(payload.draw_scenes[0].credit_cost).toBe(3)
    expect(payload.filter_scenes[0].credit_cost).toBeNull()
  })

  it('adds and removes dynamic draw scenes before saving', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-draw-scene"]').trigger('click')
    expect((wrapper.get('[data-testid="draw-scene-negative-prompt-3"]').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.get('[data-testid="draw-scene-name-3"]').setValue('赛博风')
    await wrapper.get('[data-testid="draw-scene-prompt-3"]').setValue('cyber style')
    await wrapper.get('[data-testid="draw-scene-negative-prompt-3"]').setValue('bad anatomy')
    await wrapper.get('[data-testid="remove-draw-scene-2"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes).toHaveLength(3)
    expect(payload.draw_scenes[0].name).toBe('快速自慰')
    expect(payload.draw_scenes[1].name).toBe('快速脱衣')
    expect(payload.draw_scenes[2].name).toBe('赛博风')
    expect(payload.draw_scenes[2].prompt).toBe('cyber style')
    expect(payload.draw_scenes[2].negative_prompt).toBe('bad anatomy')
    expect(payload.draw_scenes[2].engine).toBe('free_edit_v2')
    expect(payload.draw_scenes[2].lora_name).toBe('')
    expect(payload.draw_scenes[2].postprocess_draw_scene_id).toBe('')
    expect(payload.draw_scenes[2].postprocess_filter_scene_id).toBe('')
  })

  it('saves every AI drawing scene without a count limit', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: null,
      config: {
        video_scenes: [],
        filter_scenes: [],
        draw_scenes: Array.from({ length: 20 }, (_, index) => ({
          id: `draw_${index + 1}`,
          name: `绘图 ${index + 1}`,
          prompt: `prompt ${index + 1}`,
          engine: 'free_edit_v2',
        })),
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-draw-scene"]').trigger('click')
    await wrapper.get('[data-testid="draw-scene-name-20"]').setValue('绘图 21')
    await wrapper.get('[data-testid="draw-scene-prompt-20"]').setValue('prompt 21')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes).toHaveLength(21)
    expect(payload.draw_scenes[20].name).toBe('绘图 21')
  })

  it('adds and removes dynamic filter scenes before saving', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="add-filter-scene"]').trigger('click')
    expect((wrapper.get('[data-testid="filter-scene-negative-prompt-1"]').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.get('[data-testid="filter-scene-name-1"]').setValue('清晰增强')
    await wrapper.get('[data-testid="filter-scene-prompt-1"]').setValue('sharp detail')
    await wrapper.get('[data-testid="filter-scene-negative-prompt-1"]').setValue('waxy skin')
    await wrapper.get('[data-testid="remove-filter-scene-0"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.filter_scenes).toHaveLength(1)
    expect(payload.filter_scenes[0].name).toBe('清晰增强')
    expect(payload.filter_scenes[0].prompt).toBe('sharp detail')
    expect(payload.filter_scenes[0].negative_prompt).toBe('waxy skin')
    expect(payload.filter_scenes[0].engine).toBe('free_edit_v2')
    expect(payload.filter_scenes[0].lora_name).toBe('')
  })

  it('moves video, draw, and filter scenes and saves their new order', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-06-26T12:00:00',
      config: {
        video_scenes: [
          { id: 'video_a', name: '动图 A', prompt: 'video a', duration: '5s' },
          { id: 'video_b', name: '动图 B', prompt: 'video b', duration: '5s' },
        ],
        draw_scenes: [
          { id: 'draw_a', name: '绘图 A', prompt: 'draw a' },
          { id: 'draw_b', name: '绘图 B', prompt: 'draw b' },
        ],
        filter_scenes: [
          { id: 'filter_a', name: '滤镜 A', prompt: 'filter a' },
          { id: 'filter_b', name: '滤镜 B', prompt: 'filter b' },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    expect(wrapper.get('[data-testid="move-video-scene-up-0"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="move-video-scene-down-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="move-draw-scene-up-0"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="move-filter-scene-down-1"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="move-video-scene-down-0"]').trigger('click')
    await wrapper.get('[data-testid="move-draw-scene-up-1"]').trigger('click')
    await wrapper.get('[data-testid="move-filter-scene-down-0"]').trigger('click')

    expect((wrapper.get('[data-testid="video-scene-name-0"]').element as HTMLInputElement).value).toBe('动图 B')
    expect((wrapper.get('[data-testid="draw-scene-name-0"]').element as HTMLInputElement).value).toBe('绘图 B')
    expect((wrapper.get('[data-testid="filter-scene-name-0"]').element as HTMLInputElement).value).toBe('滤镜 B')

    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes.map((scene: { id: string }) => scene.id)).toEqual(['video_b', 'video_a'])
    expect(payload.draw_scenes.map((scene: { id: string }) => scene.id)).toEqual(['draw_b', 'draw_a'])
    expect(payload.filter_scenes.map((scene: { id: string }) => scene.id)).toEqual(['filter_b', 'filter_a'])
  })

  it('groups scene tables into tabs and paginates each scene kind independently', async () => {
    const makeScenes = (prefix: string, count: number) =>
      Array.from({ length: count }, (_, index) => ({
        id: `${prefix}_${index + 1}`,
        name: `${prefix.toUpperCase()} ${index + 1}`,
        prompt: `${prefix} prompt ${index + 1}`,
        duration: '5s',
      }))
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      updated_at: '2026-07-11T20:00:00',
      config: {
        video_scenes: makeScenes('video', 7),
        draw_scenes: makeScenes('draw', 6),
        filter_scenes: makeScenes('filter', 6),
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    expect(wrapper.get('[data-testid="scene-tab-video"]').text()).toContain('AI动图')
    expect(wrapper.get('[data-testid="scene-tab-draw"]').text()).toContain('AI绘图')
    expect(wrapper.get('[data-testid="scene-tab-filter"]').text()).toContain('AI滤镜')
    expect(wrapper.find('[data-testid="video-scene-name-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="video-scene-name-4"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="video-scene-name-5"]').exists()).toBe(false)

    await wrapper.get('[data-testid="video-scenes-pagination"]').get('[data-testid="pagination-next"]').trigger('click')

    expect(wrapper.find('[data-testid="video-scene-name-0"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="video-scene-name-5"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="video-scene-name-6"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="draw-scene-name-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="filter-scene-name-0"]').exists()).toBe(true)

    await wrapper.get('[data-testid="move-video-scene-up-5"]').trigger('click')
    expect(wrapper.find('[data-testid="video-scene-name-5"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="video-scene-name-4"]').element as HTMLInputElement).value).toBe('VIDEO 6')

    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes.map((scene: { id: string }) => scene.id)).toEqual([
      'video_1', 'video_2', 'video_3', 'video_4', 'video_6', 'video_5', 'video_7',
    ])
    expect(payload.draw_scenes).toHaveLength(6)
    expect(payload.filter_scenes).toHaveLength(6)
  })

  it('keeps five adjustable video LoRAs when switching to v2', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('场景配置')
    expect(wrapper.find('[data-testid="scene-config-basic-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-config-model-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-config-frame-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-end-frame-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-postprocess-select"]').exists()).toBe(false)
    const selector = wrapper.findAllComponents(SelectStub)
      .find(component => component.attributes('data-testid') === 'scene-video-lora-select')
    if (!selector) throw new Error('Missing video LoRA selector')
    expect(selector.attributes('show-search')).toBeDefined()
    expect(selector.attributes('option-filter-prop')).toBe('label')
    selector.vm.$emit('change', [
      'BreastGrow', 'BreastInsertion', 'Cum', 'Cunilingus', 'Footjob', 'Insertion',
    ])
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="scene-video-lora-strength-"]')).toHaveLength(5)
    wrapper.get('[data-testid="scene-video-lora-strength-BreastInsertion"]')
      .setValue(1.25)
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('wan22_video_v2')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.video_scenes[0].engine).toBe('wan22_video_v2')
    expect(payload.video_scenes[0].lora_name).toBe('BreastGrow')
    expect(payload.video_scenes[0].lora_strength).toBe(0.7)
    expect(payload.video_scenes[0].lora_items).toEqual([
      { name: 'BreastGrow', strength: 0.7 },
      { name: 'BreastInsertion', strength: 1.25 },
      { name: 'Cum', strength: 1 },
      { name: 'Cunilingus', strength: 0.9 },
      { name: 'Footjob', strength: 1.4 },
    ])
  })

  it('shows complete Wan22 model help without changing the selected strength', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    const selector = wrapper.findAllComponents(SelectStub)
      .find(component => component.attributes('data-testid') === 'scene-video-lora-select')
    if (!selector) throw new Error('Missing video LoRA selector')
    selector.vm.$emit('change', ['wan22_explicit_040'])
    await flushPromises()

    const strengthInput = wrapper.get(
      '[data-testid="scene-video-lora-strength-wan22_explicit_040"]',
    )
    await strengthInput.setValue(1.25)
    await getButtonByTestId(
      wrapper,
      'scene-video-lora-help-wan22_explicit_040',
    ).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('wan22_explicit_040 · 模型说明')
    expect(wrapper.text()).toContain('足部动作')
    expect(wrapper.text()).toContain('HIGH：0.80–1.10 / 推荐 1.00')
    expect(wrapper.text()).toContain('https://civitaiarchive.com/models/1861926')
    expect(wrapper.text()).toContain('提示词示例与翻译')
    expect(wrapper.text()).toContain('注意点')

    const example = wrapper.get('[data-testid="wan22-lora-prompt-example-0"]')
    expect((example.element as HTMLDetailsElement).open).toBe(false)
    await example.get('summary').trigger('click')
    expect((example.element as HTMLDetailsElement).open).toBe(true)
    expect(
      (wrapper.get(
        '[data-testid="scene-video-lora-strength-wan22_explicit_040"]',
      ).element as HTMLInputElement).value,
    ).toBe('1.25')
  })

  it('loads, changes, saves, and reloads a video scene aspect ratio', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    const ratioSelect = wrapper.get('[data-testid="scene-video-aspect-ratio-select"]')
    expect((ratioSelect.element as HTMLSelectElement).value).toBe('9:16')
    expect(ratioSelect.text()).toContain('跟随原图')
    await ratioSelect.setValue('16:9')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig.mock.calls[0][0].video_scenes[0].aspect_ratio).toBe('16:9')
    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect(
      (wrapper.get('[data-testid="scene-video-aspect-ratio-select"]').element as HTMLSelectElement).value,
    ).toBe('16:9')
  })

  it('keeps one scene draft, rejects 1024p plus 10s, and discards cancel', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-config-resolution"]').setValue('1024p')
    await wrapper.get('[data-testid="scene-config-duration"]').setValue('10s')
    await wrapper.get('[data-testid="scene-config-credit-cost"]').setValue('9')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')

    expect(antMocks.error).toHaveBeenCalledWith('AI动图不支持 1024p + 10s，请调整分辨率或时长')
    expect(wrapper.find('[data-testid="scene-model-modal"]').exists()).toBe(true)
    await wrapper.get('[data-testid="scene-config-cancel"]').trigger('click')

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect((wrapper.get('[data-testid="scene-config-resolution"]').element as HTMLSelectElement).value).toBe('720p')
    expect((wrapper.get('[data-testid="scene-config-duration"]').element as HTMLSelectElement).value).toBe('8s')
    expect((wrapper.get('[data-testid="scene-config-credit-cost"]').element as HTMLInputElement).value).toBe('')
  })

  it('saves AI video negative prompt and up to three LTX LoRAs with strengths', async () => {
    apiMocks.fetchQqccBotConfig.mockResolvedValueOnce({
      key: 'qqcc_lazy_bot_config:v1',
      config: {
        global_enabled: true,
        main_buttons: { ai_video: true },
        draw_scenes: [{
          id: 'tail', name: '尾帧', prompt: 'tail prompt', negative_prompt: '',
          engine: 'free_edit_v2', lora_name: '', postprocess_draw_scene_id: '',
          postprocess_filter_scene_id: '', original_face_swap_enabled: false,
        }],
        ai_video_scenes: [{
          id: 'cinema', name: '电影运镜', prompt: 'camera orbit', negative_prompt: '  blur  ',
          duration: 15, engine: 'ltx_video',
          lora_items: [{ path: 'ltx/a.safetensors', strength: 0.75 }],
          end_frame_draw_scene_id: 'tail',
        }],
      },
      options: {
        default_ai_video_engine: 'ltx_video',
        ai_video_engines: [{ value: 'ltx_video', supports_lora: true }],
        ltx_video_lora_models: [
          { value: 'ltx/a.safetensors', label: 'A', default_strength: 0.8 },
          { value: 'ltx/b.safetensors', label: 'B', default_strength: 1.25 },
          { value: 'ltx/c.safetensors', label: 'C', default_strength: 1 },
          { value: 'ltx/d.safetensors', label: 'D', default_strength: 1 },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    expect(wrapper.get('[data-testid="scene-tab-ai-video"]').text()).toContain('1')
    await wrapper.get('[data-testid="config-ai-video-scene-0"]').trigger('click')
    const selector = wrapper.findAllComponents(SelectStub)
      .find(component => component.attributes('data-testid') === 'scene-ai-video-lora-select')
    if (!selector) throw new Error('Missing AI video LoRA selector')
    selector.vm.$emit('change', [
      'ltx/a.safetensors', 'ltx/b.safetensors', 'ltx/c.safetensors', 'ltx/d.safetensors',
    ])
    await flushPromises()
    const loraStrengthInputs = wrapper.findAllComponents(InputNumberStub)
      .filter(component => component.attributes('data-testid')?.startsWith('scene-ai-video-lora-strength-'))
    expect(loraStrengthInputs).toHaveLength(3)
    loraStrengthInputs[1]!.vm.$emit('update:value', 1.55)
    await flushPromises()
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.main_buttons.ai_video).toBe(true)
    expect(payload.ai_video_scenes[0]).toEqual(expect.objectContaining({
      id: 'cinema',
      negative_prompt: 'blur',
      duration: 15,
      engine: 'ltx_video',
      end_frame_draw_scene_id: 'tail',
      lora_items: [
        { path: 'ltx/a.safetensors', strength: 0.75 },
        { path: 'ltx/b.safetensors', strength: 1.55 },
        { path: 'ltx/c.safetensors', strength: 1 },
      ],
    }))
  })

  it('configures a video scene end-frame draw source in the save payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-video-scene-0"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('首尾帧配置')
    expect(wrapper.find('[data-testid="scene-engine-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-lora-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="scene-end-frame-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-next-video-scene-select"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="scene-video-chain-preview"]').text()).toContain('亲吻')
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

    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('后处理配置')
    expect(wrapper.find('[data-testid="scene-engine-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-lora-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-end-frame-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="scene-postprocess-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-postprocess-filter-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-original-face-swap-switch"]').exists()).toBe(true)
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
    expect(softLightScene.postprocess_filter_scene_id).toBe('')
    expect(animeScene.postprocess_draw_scene_id).toBe('')
  })

  it('configures a draw scene to use a filter scene as postprocess template', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-2"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-postprocess-filter-select"]').text()).toContain('真实质感')
    await wrapper.get('[data-testid="scene-postprocess-filter-select"]').setValue('real_skin')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    const softLightScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light')!
    expect(softLightScene.postprocess_draw_scene_id).toBe('')
    expect(softLightScene.postprocess_filter_scene_id).toBe('real_skin')
  })

  it('configures a draw scene original face swap switch in the save payload', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-2"]').trigger('click')
    await wrapper.get('[data-testid="scene-original-face-swap-switch"]').setValue(true)
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    const softLightScene = payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light')!
    expect(softLightScene.original_face_swap_enabled).toBe(true)
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

  it('clears a draw scene filter postprocess source when the referenced filter scene is removed', async () => {
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
            postprocess_filter_scene_id: 'real_skin',
          },
        ],
        filter_scenes: [
          {
            id: 'real_skin',
            name: '真实质感',
            prompt: 'real skin prompt',
            engine: 'free_edit_v2',
            lora_name: '',
          },
        ],
      },
    })
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="remove-filter-scene-0"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes[0].postprocess_filter_scene_id).toBe('')
  })

  it('configures a draw scene to use legacy free edit with a lora model', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-2"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('模型配置')
    expect(wrapper.find('[data-testid="scene-postprocess-select"]').exists()).toBe(true)
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

  it('configures draw and filter scenes to use free edit v3 without lora', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-draw-scene-2"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('自由P图v3')
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('free_edit_v3')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')

    await wrapper.get('[data-testid="config-filter-scene-0"]').trigger('click')
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('free_edit_v3')
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.draw_scenes.find((scene: { id: string }) => scene.id === 'soft_light').engine).toBe('free_edit_v3')
    expect(payload.filter_scenes[0].engine).toBe('free_edit_v3')
    expect(payload.filter_scenes[0].lora_name).toBe('')
  })

  it('configures a filter scene model and original face swap switch', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="config-filter-scene-0"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-model-modal"]').text()).toContain('模型配置')
    expect(wrapper.find('[data-testid="scene-postprocess-select"]').exists()).toBe(false)
    await wrapper.get('[data-testid="scene-engine-select"]').setValue('free_edit')
    await wrapper.get('[data-testid="scene-lora-select"]').setValue('qwen/YARN_1.0.safetensors')
    await wrapper.get('[data-testid="scene-original-face-swap-switch"]').setValue(true)
    await wrapper.get('[data-testid="scene-config-confirm"]').trigger('click')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    const payload = apiMocks.updateQqccBotConfig.mock.calls[0][0]
    expect(payload.filter_scenes[0].engine).toBe('free_edit')
    expect(payload.filter_scenes[0].lora_name).toBe('qwen/YARN_1.0.safetensors')
    expect(payload.filter_scenes[0].original_face_swap_enabled).toBe(true)
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

  it('blocks saving incomplete dynamic filter scenes', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    await wrapper.get('[data-testid="filter-scene-prompt-0"]').setValue('')
    await wrapper.findAll('button').at(1)!.trigger('click')
    await flushPromises()

    expect(apiMocks.updateQqccBotConfig).not.toHaveBeenCalled()
    expect(antMocks.error).toHaveBeenCalledWith('请完善AI滤镜场景的按钮名称和提示词')
  })
})
