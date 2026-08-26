// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchMainBotMenuConfig: vi.fn(),
  updateMainBotMenuConfig: vi.fn(),
  fetchFeatureEntryVisibilityConfig: vi.fn(),
  updateFeatureEntryVisibilityConfig: vi.fn(),
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
      t2v: { main_model: '10eros', addon_items: [] },
      i2v: { main_model: '10eros', addon_items: [] },
      flf2v: { main_model: '10eros', addon_items: [] },
      ref2v: { main_model: '10eros', addon_items: [] },
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
        { value: '10eros', label: '10Eros TURBO' },
        { value: 'official', label: '官方高保真' },
      ],
      i2v: [
        { value: '10eros', label: '10Eros TURBO' },
        { value: 'official', label: '官方高保真' },
      ],
      flf2v: [
        { value: '10eros', label: '10Eros TURBO' },
        { value: 'official', label: '官方高保真' },
      ],
      ref2v: [
        { value: '10eros', label: '10Eros TURBO' },
        { value: 'official', label: '官方高保真' },
        { value: 'official_ref2v_turbo', label: '官方 REF2V 极速' },
      ],
    },
    addon_models: [
      {
        value: 'motion_booster',
        label: '动作强化',
        supported_modes: ['t2v', 'i2v', 'flf2v', 'ref2v'],
        default_strength: 0.7,
      },
      {
        value: 'motion_booster_ref2va',
        label: '参考人物动作强化',
        supported_modes: ['ref2v'],
        default_strength: 0.7,
      },
    ],
    max_addon_items: 13,
    strength_min: 0.1,
    strength_max: 2,
  },
})

describe('MainBotMenuSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchMainBotMenuConfig.mockResolvedValue(buildResponse())
    apiMocks.fetchFeatureEntryVisibilityConfig.mockResolvedValue(buildEntryVisibilityResponse())
    apiMocks.updateMainBotMenuConfig.mockImplementation(async (payload) => ({
      ...buildResponse(),
      config: payload,
    }))
    apiMocks.updateFeatureEntryVisibilityConfig.mockImplementation(async (payload) => ({
      ...buildEntryVisibilityResponse(),
      config: payload,
    }))
  })

  it('renders entry controls and Pro model presets as four same-level tabs', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    expect(wrapper.get('[data-testid="scope-tab-web"]').text()).toContain('Web 端')
    expect(wrapper.get('[data-testid="scope-tab-bot"]').text()).toContain('主 Bot')
    expect(wrapper.get('[data-testid="scope-tab-gallery"]').text()).toContain('修仙市集')
    expect(wrapper.get('[data-testid="scope-tab-models"]').text()).toContain('Pro 模型预设')
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
        t2v: { main_model: '10eros', addon_items: [] },
        i2v: { main_model: '10eros', addon_items: [] },
        flf2v: { main_model: '10eros', addon_items: [] },
        ref2v: { main_model: '10eros', addon_items: [] },
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
    await wrapper.get('[data-testid="avp-main-model-i2v"]').setValue('official')
    await wrapper.get('[data-testid="avp-addon-models-i2v"]').setValue(['motion_booster'])
    await wrapper.get('[data-testid="avp-addon-strength-i2v-motion_booster"]').setValue('1.25')
    await wrapper.get('[data-testid="save-advanced-video-pro-config"]').trigger('click')
    await flushPromises()

    const payload = apiMocks.updateFeatureEntryVisibilityConfig.mock.calls[0][0]
    expect(payload.advanced_video_pro.i2v).toEqual({
      main_model: 'official',
      addon_items: [{ name: 'motion_booster', strength: 1.25 }],
    })
    expect(messageMocks.success).toHaveBeenCalledWith('Pro 模型预设已保存')
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
