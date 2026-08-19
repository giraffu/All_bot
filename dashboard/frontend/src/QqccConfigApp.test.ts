// @vitest-environment jsdom

import { defineComponent, nextTick, ref } from 'vue'
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
  uploadQqccDemoMedia: vi.fn(),
  generateQqccDemoMedia: vi.fn(),
  getQqccDemoGeneration: vi.fn(),
}))

const componentStubs = vi.hoisted(() => ({
  LoginStub: {
    name: 'QqccConfigLoginStub',
    template: '<div class="qqcc-login-stub">login</div>',
  },
  SettingsStub: {
    name: 'QqccBotSettingsStub',
    props: ['fetchConfig', 'updateConfig', 'uploadDemoMedia', 'generateDemoMedia', 'getDemoGeneration'],
    template: '<div class="qqcc-settings-stub">settings</div>',
  },
  PrivateBotAdminStub: {
    name: 'PrivateBotAdminManagerStub',
    template: '<div class="private-bot-admin-stub">private bots</div>',
  },
}))

vi.mock('./components/QqccConfigLogin.vue', () => ({
  default: componentStubs.LoginStub,
}))

vi.mock('./components/QqccBotSettings.vue', () => ({
  default: componentStubs.SettingsStub,
}))

vi.mock('./components/PrivateBotAdminManager.vue', () => ({
  default: componentStubs.PrivateBotAdminStub,
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
        'a-radio-group': defineComponent({
          props: ['value'],
          emits: ['update:value'],
          template: `
            <div>
              <button class="private-bot-view-button" type="button" @click="$emit('update:value', 'private-bots')">私有Bot管理</button>
              <slot />
            </div>
          `,
        }),
        'a-radio-button': defineComponent({ template: '<span><slot /></span>' }),
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
    expect(settings.props('uploadDemoMedia')).toBe(apiMocks.uploadQqccDemoMedia)

    await wrapper.find('.logout-button').trigger('click')

    expect(qqccAuthMocks.clearAuthToken).toHaveBeenCalledOnce()
  })

  it('switches from the official config to private Bot management', async () => {
    qqccAuthMocks.isAuthenticatedRef = ref(true)
    const wrapper = mountApp()

    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(true)
    expect(wrapper.find('.private-bot-admin-stub').exists()).toBe(false)

    await wrapper.get('.private-bot-view-button').trigger('click')

    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(false)
    expect(wrapper.find('.private-bot-admin-stub').exists()).toBe(true)
  })

  it('keeps the edited settings mounted while an expired login is renewed', async () => {
    qqccAuthMocks.isAuthenticatedRef = ref(true)
    const wrapper = mountApp()

    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(true)

    qqccAuthMocks.isAuthenticatedRef.value = false
    await nextTick()

    expect(wrapper.find('.qqcc-login-stub').exists()).toBe(true)
    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(true)

    qqccAuthMocks.isAuthenticatedRef.value = true
    await nextTick()

    expect(wrapper.find('.qqcc-login-stub').exists()).toBe(false)
    expect(wrapper.find('.qqcc-settings-stub').exists()).toBe(true)
  })
})
