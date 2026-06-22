// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import i18n from '@/i18n'
import Profile from '@/views/Profile.vue'

const { authStoreMock, themeStoreMock, templateApplyStoreMock, apiGetMock, routerPushMock } =
  vi.hoisted(() => ({
    authStoreMock: {
      token: 'token',
      user: {
        id: 1,
        telegram_id: 123456789,
        username: 'tester',
        full_name: 'Tester',
        language_code: 'zh',
        credits: 999,
        user_group: '练气期',
        current_identity: '外门弟子',
        identity_expire_at: null,
        priority: 0,
        generation_count: 12,
        checkin_count: 5,
        invitation_count: 8,
        invitation_recharge: {
          recharged_invitees_count: 3,
          total_recharge_count: 5,
          total_ton: 0,
          total_rmb: 0,
          total_stars: 0,
          commission_usdt: 0,
          total_commission_usdt: 300,
          spent_commission_usdt: 67.65,
          available_balance_usdt: 232.35,
        },
      },
      fetchUser: vi.fn().mockResolvedValue(undefined),
      setAuth: vi.fn(),
    },
    themeStoreMock: {
      selectedTheme: 'system',
      effectiveTheme: 'light',
      setTheme: vi.fn(),
      initTheme: vi.fn(),
    },
    templateApplyStoreMock: {
      openWithPost: vi.fn(),
      close: vi.fn(),
    },
    apiGetMock: vi.fn(),
    routerPushMock: vi.fn(),
  }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreMock,
}))

vi.mock('@/stores/theme', () => ({
  useThemeStore: () => themeStoreMock,
}))

vi.mock('@/stores/templateApply', () => ({
  useTemplateApplyStore: () => templateApplyStoreMock,
}))

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRouter: () => ({
      push: routerPushMock,
    }),
  }
})

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock,
    patch: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/composables/useViewport', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  return {
    useViewport: () => ({
      isMobile: ref(false),
    }),
  }
})

vi.mock('@/composables/useTelegram', () => ({
  useTelegram: () => ({
    showMainButton: vi.fn(),
    hideMainButton: vi.fn(),
    hapticFeedback: vi.fn(),
    isTMA: false,
  }),
}))

vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<object>('ant-design-vue')
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

const slotStub = (name: string) =>
  defineComponent({
    name,
    template: '<div><slot /></div>',
  })

describe('Profile affiliate commission display', () => {
  beforeEach(() => {
    authStoreMock.fetchUser.mockClear()
    apiGetMock.mockReset()
    routerPushMock.mockReset()
    apiGetMock.mockResolvedValue({
      data: {
        comfy_online: true,
        queue_size: 0,
        queue_by_type: {},
      },
    })
  })

  it('renders total, spent, and available commission from invitation stats', async () => {
    const wrapper = mount(Profile, {
      global: {
        plugins: [i18n],
        stubs: {
          'a-card': slotStub('ACardStub'),
          'a-button': slotStub('AButtonStub'),
          'a-modal': slotStub('AModalStub'),
          'a-radio-group': slotStub('ARadioGroupStub'),
          'a-radio': slotStub('ARadioStub'),
          Wallet: true,
          Activity: true,
          CalendarCheck: true,
          Zap: true,
          Award: true,
          User: true,
          Clock: true,
          Lock: true,
          Bookmark: true,
          Star: true,
        },
        renderStubDefaultSlot: true,
      },
    })

    await flushPromises()

    const text = wrapper.text()
    expect(authStoreMock.fetchUser).toHaveBeenCalled()
    expect(text).toContain('受邀者首笔充值(TON)')
    expect(text).toContain('受邀者首笔充值(人民币)')
    expect(text).toContain('受邀者首笔充值(Stars)')
    expect(text).toContain('历史累计返佣')
    expect(text).toContain('$ 300.00 USDT')
    expect(text).toContain('已兑换返佣')
    expect(text).toContain('$ 67.65 USDT')
    expect(text).toContain('当前可兑换返佣')
    expect(text).toContain('$ 232.3500 USDT')
  })

  it('routes billing quick action to the billing page', async () => {
    const wrapper = mount(Profile, {
      global: {
        plugins: [i18n],
        stubs: {
          'a-card': slotStub('ACardStub'),
          'a-button': slotStub('AButtonStub'),
          'a-modal': slotStub('AModalStub'),
          'a-radio-group': slotStub('ARadioGroupStub'),
          'a-radio': slotStub('ARadioStub'),
          Wallet: true,
          Activity: true,
          CalendarCheck: true,
          Zap: true,
          Award: true,
          User: true,
          Lock: true,
          Bookmark: true,
          Star: true,
        },
        renderStubDefaultSlot: true,
      },
    })

    await flushPromises()

    const billingAction = wrapper.find('[data-testid="quick-action-billing"]')
    expect(billingAction.exists()).toBe(true)

    await billingAction.trigger('click')

    expect(routerPushMock).toHaveBeenCalledWith('/billing')
  })
})
