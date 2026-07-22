// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  apiPostMock,
  messageErrorMock,
  routerPushMock,
  setAuthMock,
  checkWebAccessMock,
  routeQueryMock,
} = vi.hoisted(() => ({
  apiPostMock: vi.fn(),
  messageErrorMock: vi.fn(),
  routerPushMock: vi.fn(),
  setAuthMock: vi.fn(),
  checkWebAccessMock: vi.fn(),
  routeQueryMock: {} as Record<string, unknown>,
}))

vi.mock('@/api', () => ({
  default: {
    post: apiPostMock,
  },
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error: messageErrorMock,
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('@ant-design/icons-vue', () => ({
  LockOutlined: { template: '<span />' },
  UserOutlined: { template: '<span />' },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQueryMock }),
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    setAuth: setAuthMock,
  }),
  checkWebAccess: checkWebAccessMock,
}))

describe('Login Mini App auth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    window.history.replaceState(null, '', '/login')
    checkWebAccessMock.mockReturnValue(true)
    Object.keys(routeQueryMock).forEach((key) => delete routeQueryMock[key])
    ;(window as any).Telegram = {
      WebApp: {
        initData: 'tg-init-data',
        platform: 'ios',
      },
    }
  })

  it('shows the backend denial reason when Telegram Mini App auth fails', async () => {
    const denialMessage = '权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端'
    apiPostMock.mockRejectedValueOnce({
      response: {
        data: {
          detail: denialMessage,
        },
      },
    })

    const { default: Login } = await import('./Login.vue')
    const wrapper = mount(Login, {
      global: {
        stubs: {
          'a-button': { template: '<button><slot /></button>' },
          'a-input': { template: '<input />' },
          'a-input-password': { template: '<input />' },
          'a-spin': { template: '<div><slot /></div>' },
        },
      },
    })

    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith('/auth/telegram', {
      initData: 'tg-init-data',
    })
    expect(wrapper.text()).toContain(denialMessage)
    expect(messageErrorMock).toHaveBeenCalledWith(denialMessage)
  }, 10000)

  it('uses Telegram launch init data when the WebApp SDK object is unavailable', async () => {
    const initData = 'query_id=abc&user=%7B%22id%22%3A123456%2C%22first_name%22%3A%22AAaa%22%7D&auth_date=1760000000&hash=deadbeef'
    ;(window as any).Telegram = undefined
    window.history.replaceState(
      null,
      '',
      `/login#tgWebAppData=${encodeURIComponent(initData)}&tgWebAppVersion=7.0&tgWebAppPlatform=android`
    )
    apiPostMock.mockResolvedValueOnce({
      data: {
        access_token: 'token',
        user: { id: 1, telegram_id: 123456, user_group: '练气期', current_identity: '外门弟子' },
      },
    })

    const { default: Login } = await import('./Login.vue')
    mount(Login, {
      global: {
        stubs: {
          'a-button': { template: '<button><slot /></button>' },
          'a-input': { template: '<input />' },
          'a-input-password': { template: '<input />' },
          'a-spin': { template: '<div><slot /></div>' },
        },
      },
    })

    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith('/auth/telegram', { initData })
    expect(setAuthMock).toHaveBeenCalledWith('token', {
      id: 1,
      telegram_id: 123456,
      user_group: '练气期',
      current_identity: '外门弟子',
    }, 'full')
    expect(routerPushMock).toHaveBeenCalledWith('/profile')
  }, 10000)

  it('uses payment auth and returns to the TON billing deep link', async () => {
    routeQueryMock.redirect = '/billing?method=ton&kind=membership'
    checkWebAccessMock.mockReturnValue(false)
    apiPostMock.mockResolvedValueOnce({
      data: {
        access_token: 'payment-token',
        user: {
          id: 2,
          telegram_id: 654321,
          credits: 6,
          user_group: '凡人',
          current_identity: '外门弟子',
        },
      },
    })

    const { default: Login } = await import('./Login.vue')
    mount(Login, {
      global: {
        stubs: {
          'a-button': { template: '<button><slot /></button>' },
          'a-input': { template: '<input />' },
          'a-input-password': { template: '<input />' },
          'a-spin': { template: '<div><slot /></div>' },
        },
      },
    })

    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith('/auth/telegram/payment', {
      initData: 'tg-init-data',
    })
    expect(checkWebAccessMock).not.toHaveBeenCalled()
    expect(setAuthMock).toHaveBeenCalledWith('payment-token', {
      id: 2,
      telegram_id: 654321,
      credits: 6,
      user_group: '凡人',
      current_identity: '外门弟子',
    }, 'payment')
    expect(routerPushMock).toHaveBeenCalledWith(
      '/billing?method=ton&kind=membership'
    )
  }, 10000)
})
