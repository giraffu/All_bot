// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchMainBotMenuConfig: vi.fn(),
  updateMainBotMenuConfig: vi.fn(),
  fetchFeatureEntryVisibilityConfig: vi.fn(),
  updateFeatureEntryVisibilityConfig: vi.fn(),
  fetchTaskPricingConfig: vi.fn(),
  updateTaskPricingConfig: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)
vi.mock('ant-design-vue/es/message', () => ({ default: messageMocks }))

import MainBotMenuSettings from './MainBotMenuSettings.vue'

const mainItems = [
  'menu.lazy_bot',
  'menu.recharge',
  'menu.checkin',
  'menu.profile',
  'menu.share',
  'menu.queue',
  'menu.switch_lang',
  'menu.photo_edit',
  'menu.video_to_video',
  'menu.txt2img',
  'menu.i2i_pro',
  'menu.free_edit',
  'menu.video_lora',
  'menu.ltx_video',
  'menu.advanced_video_pro',
  'menu.wan22_video_v2',
]

const buildResponse = () => ({
  key: 'main_bot_menu_config:v1',
  updated_at: null,
  config: {
    main_menu: {
      buttons_per_row: 3,
      items: mainItems.map((key) => ({ key, visible: true })),
    },
    submenus: {
      'menu.photo_edit': [
        { key: 'menu.photo_edit_faceswap', visible: true },
        { key: 'menu.photo_edit_random_faceswap', visible: false },
      ],
      'menu.video_to_video': [
        { key: 'menu.video_to_video_replacement', visible: true },
        { key: 'menu.video_to_video_action_transfer', visible: true },
        { key: 'menu.face_video', visible: true },
      ],
    },
  },
})

const buildEntryVisibilityResponse = () => ({
  key: 'feature_entry_visibility_config:v1',
  updated_at: null,
  config: {
    web: {
      edit: true,
      edit_v2_5: true,
      edit_v3: true,
      txt2img: true,
      i2i_pro: true,
      custom_video: true,
      face_swap: true,
      random_faceswap: true,
      ltx_video: true,
      ltx_video_v2: true,
      ltx_t2v: true,
      minimax_h3: false,
      wan22_video_v2: true,
      scail2_action_transfer: true,
      scail2_video_replacement: true,
      scail2_face_swap_v2: true,
      character_assets: false,
    },
    gallery: {
      txt2img: true,
      i2i_pro: true,
      edit: true,
      free_edit_v2_5: true,
      free_edit_v3: true,
      custom_video: true,
      ltx_video: true,
      minimax_h3: false,
      wan22_video_v2: true,
      scail2_action_transfer: true,
      scail2_video_replacement: true,
      scail2_face_swap_v2: true,
    },
    advanced_video_pro: {
      t2v: { main_model: '10eros_bf16', addon_items: [] },
      i2v: { main_model: '10eros_bf16', addon_items: [] },
      flf2v: { main_model: '10eros_bf16', addon_items: [] },
      ref2v: { main_model: '10eros_bf16', addon_items: [] },
    },
  },
  options: {
    modes: [
      { value: 't2v', label: '文生视频' },
      { value: 'i2v', label: '首帧图生视频' },
      { value: 'flf2v', label: '首尾帧视频' },
      { value: 'ref2v', label: '参考图生视频' },
    ],
    main_models: {
      t2v: [
        { value: '10eros_bf16', label: '10Eros Beta4 BF16' },
        { value: '10eros_int8', label: '10Eros Beta4 INT8 ConvRot' },
      ],
      i2v: [
        { value: '10eros_bf16', label: '10Eros Beta4 BF16' },
        { value: '10eros_int8', label: '10Eros Beta4 INT8 ConvRot' },
      ],
      flf2v: [
        { value: '10eros_bf16', label: '10Eros Beta4 BF16' },
        { value: '10eros_int8', label: '10Eros Beta4 INT8 ConvRot' },
      ],
      ref2v: [
        { value: '10eros_bf16', label: '10Eros Beta4 BF16' },
        { value: '10eros_int8', label: '10Eros Beta4 INT8 ConvRot' },
      ],
    },
    addon_models: [
      {
        value: 'deepthroat',
        label: 'Daring Deepthroat v0.2（深喉动作）',
        supported_modes: ['t2v', 'i2v', 'flf2v', 'ref2v'],
        default_strength: 0.7,
      },
      {
        value: 'pov_missionary',
        label: 'H3 POV Missionary v0.7（POV 传教士动作）',
        supported_modes: ['t2v', 'i2v', 'flf2v', 'ref2v'],
        default_strength: 0.7,
      },
      {
        value: 'footjob',
        label: 'H3 Footjobs Type B v1（足交动作）',
        supported_modes: ['t2v', 'i2v', 'flf2v', 'ref2v'],
        default_strength: 0.5,
      },
      {
        value: 'cumshot',
        label: 'HMCumshot v0.5（射精动作）',
        supported_modes: ['t2v', 'i2v', 'flf2v', 'ref2v'],
        default_strength: 0.9,
      },
    ],
    max_addon_items: 4,
    strength_min: 0.1,
    strength_max: 2,
  },
})

const buildTaskPricingResponse = () => ({
  key: 'task_pricing_config:v1',
  schema_version: 2,
  updated_at: null,
  prices: { txt2img: 9 },
  overrides: { txt2img: 9 },
  categories: [
    {
      id: 'image_generation',
      label: '图片生成',
      offers: [{
        id: 'txt2img',
        label: '文生图',
        description: '文字生成图片',
        dimensions: [],
        variants: [{
          variant_id: 'txt2img',
          task_types: ['txt2img'],
          conditions: {},
          default_cost: 2,
          override_cost: 9,
          effective_cost: 9,
        }],
      }],
    },
    {
      id: 'image_editing',
      label: '图片编辑',
      offers: [{
        id: 'free_edit_v2_5',
        label: '自由 P 图 v2.5',
        description: '单图编辑与双图融合分别定价',
        dimensions: [{
          key: 'input_count',
          label: '输入图片',
          options: [
            { value: '1', label: '1 个输入' },
            { value: '2', label: '2 个输入' },
          ],
        }],
        variants: [
          {
            variant_id: 'free_edit_v2_5::input_count=1',
            task_types: ['free_edit_v2_5'],
            conditions: { input_count: '1' },
            default_cost: 3,
            override_cost: null,
            effective_cost: 3,
          },
          {
            variant_id: 'free_edit_v2_5::input_count=2',
            task_types: ['free_edit_v2_5'],
            conditions: { input_count: '2' },
            default_cost: 7,
            override_cost: null,
            effective_cost: 7,
          },
        ],
      }],
    },
    {
      id: 'video_generation',
      label: '视频生成',
      offers: [{
        id: 'advanced_video_pro',
        label: '高级图生视频 Pro',
        description: '按生成方式、清晰度、时长和参考音视频定价',
        dimensions: [
          { key: 'mode', label: '生成方式', options: [{ value: 'i2v', label: '首帧图生视频' }] },
          { key: 'resolution', label: '清晰度', options: [{ value: 'preview', label: '极速' }] },
          { key: 'duration', label: '时长', options: [{ value: '5', label: '5 秒' }] },
          { key: 'reference_audio', label: '参考音频', options: [{ value: 'no', label: '无' }] },
          { key: 'reference_video', label: '参考视频', options: [{ value: 'no', label: '无' }] },
        ],
        variants: [{
          variant_id: 'advanced_video_pro::mode=i2v::resolution=preview::duration=5::reference_audio=no::reference_video=no',
          task_types: ['minimax_h3_i2v'],
          conditions: { mode: 'i2v', resolution: 'preview', duration: '5', reference_audio: 'no', reference_video: 'no' },
          default_cost: 10,
          override_cost: null,
          effective_cost: 10,
        }],
      }],
    },
  ],
})

describe('MainBotMenuSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchMainBotMenuConfig.mockResolvedValue(buildResponse())
    apiMocks.fetchFeatureEntryVisibilityConfig.mockResolvedValue(buildEntryVisibilityResponse())
    apiMocks.fetchTaskPricingConfig.mockResolvedValue(buildTaskPricingResponse())
    apiMocks.updateMainBotMenuConfig.mockImplementation(async (payload) => ({
      ...buildResponse(),
      config: payload,
    }))
    apiMocks.updateFeatureEntryVisibilityConfig.mockImplementation(async (payload) => ({
      ...buildEntryVisibilityResponse(),
      config: payload,
    }))
    apiMocks.updateTaskPricingConfig.mockImplementation(async (payload) => ({
      ...buildTaskPricingResponse(),
      prices: payload.prices,
      categories: buildTaskPricingResponse().categories.map(category => ({
        ...category,
        offers: category.offers.map(offer => ({
          ...offer,
          variants: offer.variants.map(variant => ({
            ...variant,
            override_cost: payload.prices[variant.variant_id] ?? null,
            effective_cost: payload.prices[variant.variant_id] ?? variant.default_cost,
          })),
        })),
      })),
    }))
  })

  it('renders entry controls, Pro model presets, and task pricing as same-level tabs', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    expect(wrapper.get('[data-testid="scope-tab-web"]').text()).toContain('Web 端')
    expect(wrapper.get('[data-testid="scope-tab-bot"]').text()).toContain('主 Bot')
    expect(wrapper.get('[data-testid="scope-tab-gallery"]').text()).toContain('修仙市集')
    expect(wrapper.get('[data-testid="scope-tab-models"]').text()).toContain('Pro 模型预设')
    expect(wrapper.get('[data-testid="scope-tab-pricing"]').text()).toContain('任务定价')
    expect(wrapper.find('[data-testid="web-entry-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="bot-entry-panel"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('自由P图')
    expect(wrapper.text()).toContain('图生视频')
    expect(wrapper.text()).toContain('高级图生视频 Pro')
    expect(wrapper.text()).not.toContain('高级图生视频 Pro 模型预设')

    await wrapper.get('[data-testid="scope-tab-bot"]').trigger('click')
    expect(wrapper.find('[data-testid="web-entry-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="bot-entry-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('懒人bot')
    expect(wrapper.text()).toContain('图片换脸 · 二级菜单')
    expect(wrapper.text()).toContain('快速换脸')
    expect(wrapper.text()).toContain('视频生视频 · 二级菜单')
    expect(wrapper.text()).toContain('视频换脸')
    expect(wrapper.text()).toContain('返回主菜单固定可见')
    expect(wrapper.get('[data-testid="status-menu-photo_edit_random_faceswap"]').text()).toBe('隐藏')

    await wrapper.get('[data-testid="scope-tab-gallery"]').trigger('click')
    expect(wrapper.find('[data-testid="bot-entry-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="gallery-entry-panel"]').exists()).toBe(true)

    await wrapper.get('[data-testid="scope-tab-models"]').trigger('click')
    expect(wrapper.find('[data-testid="gallery-entry-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="advanced-video-pro-panel"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="scope-tab-models"]').classes()).toContain('is-active')
    expect(wrapper.get('[data-testid="scope-tab-web"]').classes()).not.toContain('is-active')
    expect(wrapper.text()).toContain('高级图生视频 Pro 模型预设')

    await wrapper.get('[data-testid="scope-tab-pricing"]').trigger('click')
    expect(wrapper.find('[data-testid="advanced-video-pro-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="task-pricing-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('文生图')
    expect(wrapper.text()).toContain('系统默认 2 灵石')
    expect(wrapper.text()).not.toContain('口交黑人')
  })

  it('selects a child condition and saves only that pricing variant', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="scope-tab-pricing"]').trigger('click')
    await wrapper.get('[data-testid="pricing-category-select"]').setValue('image_editing')
    await wrapper.get('[data-testid="pricing-dimension-input_count"]').setValue('2')
    expect(wrapper.text()).toContain('系统默认 7 灵石')
    await wrapper.get('[data-testid="selected-task-price"]').setValue('11')
    await wrapper.get('[data-testid="save-task-pricing"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateTaskPricingConfig).toHaveBeenCalledWith({
      schema_version: 2,
      prices: {
        txt2img: 9,
        'free_edit_v2_5::input_count=2': 11,
      },
    })
    expect(messageMocks.success).toHaveBeenCalledWith('任务定价已保存，Web 与主 Bot 新任务立即统一生效')
  })

  it('saves Web and market visibility separately from the Bot menu', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="entry-web-edit"]').setValue(false)
    await wrapper.get('[data-testid="entry-web-custom_video"]').setValue(false)
    await wrapper.get('[data-testid="entry-web-minimax_h3"]').setValue(true)
    await wrapper.get('[data-testid="save-web-entry-visibility"]').trigger('click')
    await wrapper.get('[data-testid="scope-tab-gallery"]').trigger('click')
    await wrapper.get('[data-testid="entry-gallery-minimax_h3"]').setValue(true)
    await wrapper.get('[data-testid="save-gallery-entry-visibility"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateFeatureEntryVisibilityConfig).toHaveBeenLastCalledWith({
      web: {
        edit: false,
        edit_v2_5: true,
        edit_v3: true,
        txt2img: true,
        i2i_pro: true,
        custom_video: false,
        face_swap: true,
        random_faceswap: true,
        ltx_video: true,
        ltx_video_v2: true,
        ltx_t2v: true,
        minimax_h3: true,
        wan22_video_v2: true,
        scail2_action_transfer: true,
        scail2_video_replacement: true,
        scail2_face_swap_v2: true,
        character_assets: false,
      },
      gallery: {
        txt2img: true,
        i2i_pro: true,
        edit: true,
        free_edit_v2_5: true,
        free_edit_v3: true,
        custom_video: true,
        ltx_video: true,
        minimax_h3: true,
        wan22_video_v2: true,
        scail2_action_transfer: true,
        scail2_video_replacement: true,
        scail2_face_swap_v2: true,
      },
      advanced_video_pro: {
        t2v: { main_model: '10eros_bf16', addon_items: [] },
        i2v: { main_model: '10eros_bf16', addon_items: [] },
        flf2v: { main_model: '10eros_bf16', addon_items: [] },
        ref2v: { main_model: '10eros_bf16', addon_items: [] },
      },
    })
    expect(apiMocks.updateMainBotMenuConfig).not.toHaveBeenCalled()
    expect(messageMocks.success).toHaveBeenCalledWith('Web 端入口配置已保存')
    expect(messageMocks.success).toHaveBeenCalledWith('修仙市集入口配置已保存')
  })

  it('saves main models and per-addon strengths from the dedicated preset tab', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="scope-tab-models"]').trigger('click')
    await wrapper.get('[data-testid="avp-main-model-i2v"]').setValue('10eros_int8')
    await wrapper.get('[data-testid="avp-addon-checkbox-i2v-deepthroat"]').setValue(true)
    await wrapper.get('[data-testid="avp-addon-checkbox-i2v-pov_missionary"]').setValue(true)
    await wrapper.get('[data-testid="avp-addon-strength-i2v-deepthroat"]').setValue('1.25')
    await wrapper.get('[data-testid="save-advanced-video-pro-config"]').trigger('click')
    await flushPromises()

    const payload = apiMocks.updateFeatureEntryVisibilityConfig.mock.calls[0][0]
    expect(payload.advanced_video_pro.i2v).toEqual({
      main_model: '10eros_int8',
      addon_items: [
        { name: 'deepthroat', strength: 1.25 },
        { name: 'pov_missionary', strength: 0.7 },
      ],
    })
    expect(messageMocks.success).toHaveBeenCalledWith('Pro 模型预设已保存')
  })

  it('allows every mode to save no addon model by leaving all checkboxes clear', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="scope-tab-models"]').trigger('click')
    const checkbox = wrapper.get('[data-testid="avp-addon-checkbox-t2v-deepthroat"]')
    await checkbox.setValue(true)
    await checkbox.setValue(false)
    await wrapper.get('[data-testid="save-advanced-video-pro-config"]').trigger('click')
    await flushPromises()

    const payload = apiMocks.updateFeatureEntryVisibilityConfig.mock.calls[0][0]
    expect(payload.advanced_video_pro.t2v.addon_items).toEqual([])
    expect(wrapper.text()).toContain('不勾选即不使用附加模型')
  })

  it('changes row size, visibility, and main-menu order before saving', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="scope-tab-bot"]').trigger('click')
    await wrapper.get('[data-testid="buttons-per-row"]').setValue('4')
    await wrapper.get('[data-testid="visibility-menu-lazy_bot"]').setValue(false)
    await wrapper.get('[data-testid="move-down-menu-lazy_bot"]').trigger('click')
    await wrapper.get('[data-testid="save-main-bot-menu"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateMainBotMenuConfig).toHaveBeenCalledTimes(1)
    const payload = apiMocks.updateMainBotMenuConfig.mock.calls[0][0]
    expect(payload.main_menu.buttons_per_row).toBe(4)
    expect(payload.main_menu.items.slice(0, 2).map((item: { key: string }) => item.key)).toEqual([
      'menu.recharge',
      'menu.lazy_bot',
    ])
    expect(payload.main_menu.items[1].visible).toBe(false)
    expect(messageMocks.success).toHaveBeenCalledWith('主 Bot 菜单配置已保存')
  })

  it('keeps ordering boundaries disabled and reports API failures', async () => {
    apiMocks.updateMainBotMenuConfig.mockRejectedValueOnce(new Error('failed'))
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    await wrapper.get('[data-testid="scope-tab-bot"]').trigger('click')
    expect(wrapper.get('[data-testid="move-up-menu-lazy_bot"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="move-down-menu-wan22_video_v2"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="save-main-bot-menu"]').trigger('click')
    await flushPromises()

    expect(messageMocks.error).toHaveBeenCalledWith('保存主 Bot 菜单配置失败')
  })
})
