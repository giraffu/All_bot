// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  apiPostMock,
  messageErrorMock,
  routerPushMock,
  setAuthMock,
  checkWebAccessMock,
} = vi.hoisted(() => ({
  apiPostMock: vi.fn(),
  messageErrorMock: vi.fn(),
  routerPushMock: vi.fn(),
  setAuthMock: vi.fn(),
  checkWebAccessMock: vi.fn(),
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
  useRoute: () => ({ query: {} }),
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
  })
})
