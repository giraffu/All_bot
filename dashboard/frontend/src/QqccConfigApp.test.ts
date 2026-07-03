// @vitest-environment jsdom

import { defineComponent, ref } from 'vue'
import type { Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Mock } from 'vitest'

const qqccAuthMocks = vi.hoisted<{
  isAuthenticatedRef: Ref<boolean> | null
  clearAuthToken: Mock
}>(() => ({
  isAuthenticatedRef: null,
  clearAuthToken: vi.fn(),
}))

const apiMocks = vi.hoisted(() => ({
  fetchQqccConfig: vi.fn(),
  updateQqccConfig: vi.fn(),
}))

const componentStubs = vi.hoisted(() => ({
  LoginStub: {
    name: 'QqccConfigLoginStub',
    template: '<div class="qqcc-login-stub">login</div>',
  },
  SettingsStub: {
    name: 'QqccBotSettingsStub',
    props: ['fetchConfig', 'updateConfig'],
    template: '<div class="qqcc-settings-stub">settings</div>',
  },
}))

vi.mock('./components/QqccConfigLogin.vue', () => ({
  default: componentStubs.LoginStub,
}))

vi.mock('./components/QqccBotSettings.vue', () => ({
  default: componentStubs.SettingsStub,
}))

vi.mock('./api/qqccConfigApi', () => apiMocks)

vi.mock('./composables/useQqccConfigAuth', async () => {
  const vue = await vi.importActual<typeof import('vue')>('vue')
  qqccAuthMocks.isAuthenticatedRef ??= vue.ref(false)
  return {
    useQqccConfigAuth: () => ({
      isAuthenticated: qqccAuthMocks.isAuthenticatedRef,
      clearAuthToken: qqccAuthMocks.clearAuthToken,
    }),
  }
})

import QqccConfigApp from './QqccConfigApp.vue'

const mountApp = () =>
  mount(QqccConfigApp, {
    global: {
      stubs: {
        'a-layout': defineComponent({ template: '<div><slot /></div>' }),
        'a-layout-header': defineComponent({ template: '<header><slot /></header>' }),
        'a-layout-content': defineComponent({ template: '<main><slot /></main>' }),
        'a-button': defineComponent({
          emits: ['click'],
          template:
            '<button type="button" class="logout-button" @click="$emit(\'click\')"><slot /></button>',
        }),
      },
    },
  })

describe('QqccConfigApp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    qqccAuthMocks.isAuthenticatedRef = ref(false)
  })

  it('renders the dedicated login screen when unauthenticated', () => {
    const wrapper = mountApp()

    expect(wrapper.find('.qqcc-login-stub').exists()).toBe(true)
    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(false)
  })

  it('renders settings with dedicated API handlers and supports logout', async () => {
    qqccAuthMocks.isAuthenticatedRef = ref(true)
    const wrapper = mountApp()

    const settings = wrapper.findComponent(componentStubs.SettingsStub)
    expect(settings.exists()).toBe(true)
    expect(settings.props('fetchConfig')).toBe(apiMocks.fetchQqccConfig)
    expect(settings.props('updateConfig')).toBe(apiMocks.updateQqccConfig)

    await wrapper.find('.logout-button').trigger('click')

    expect(qqccAuthMocks.clearAuthToken).toHaveBeenCalledOnce()
  })
})
