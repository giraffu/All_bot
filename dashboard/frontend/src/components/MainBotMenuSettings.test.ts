// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchMainBotMenuConfig: vi.fn(),
  updateMainBotMenuConfig: vi.fn(),
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

describe('MainBotMenuSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchMainBotMenuConfig.mockResolvedValue(buildResponse())
    apiMocks.updateMainBotMenuConfig.mockImplementation(async (payload) => ({
      ...buildResponse(),
      config: payload,
    }))
  })

  it('renders the main and second-level menu hierarchy with visibility labels', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

    expect(wrapper.text()).toContain('主 Bot 菜单')
    expect(wrapper.text()).toContain('懒人bot')
    expect(wrapper.text()).toContain('图片换脸 · 二级菜单')
    expect(wrapper.text()).toContain('快速换脸')
    expect(wrapper.text()).toContain('视频生视频 · 二级菜单')
    expect(wrapper.text()).toContain('视频换脸')
    expect(wrapper.text()).toContain('返回主菜单固定可见')
    expect(wrapper.get('[data-testid="status-menu-photo_edit_random_faceswap"]').text()).toBe('隐藏')
  })

  it('changes row size, visibility, and main-menu order before saving', async () => {
    const wrapper = mount(MainBotMenuSettings)
    await flushPromises()

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

    expect(wrapper.get('[data-testid="move-up-menu-lazy_bot"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="move-down-menu-wan22_video_v2"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="save-main-bot-menu"]').trigger('click')
    await flushPromises()

    expect(messageMocks.error).toHaveBeenCalledWith('保存主 Bot 菜单配置失败')
  })
})
