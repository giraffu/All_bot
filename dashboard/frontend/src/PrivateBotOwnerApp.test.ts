// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  exchangePrivateBotOwnerTicket: vi.fn(),
  fetchPrivateBotOwnerMe: vi.fn(),
  pausePrivateBotOwner: vi.fn(),
  resumePrivateBotOwner: vi.fn(),
  retryPrivateBotOwner: vi.fn(),
  updatePrivateBotOwnerConfig: vi.fn(),
  updatePrivateBotOwnerCredentials: vi.fn(),
  uploadPrivateBotOwnerDemoMedia: vi.fn(),
  generatePrivateBotOwnerDemoMedia: vi.fn(),
  getPrivateBotOwnerDemoGeneration: vi.fn(),
}))

const authMocks = vi.hoisted(() => ({
  getAuthToken: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

const SettingsStub = vi.hoisted(() => ({
  name: 'QqccBotSettingsStub',
  props: ['fetchConfig', 'updateConfig', 'uploadDemoMedia', 'generateDemoMedia', 'getDemoGeneration', 'demoMediaObjectPrefixes'],
  template: '<div class="settings-stub">settings</div>',
}))

vi.mock('./api/privateBotOwnerApi', () => apiMocks)
vi.mock('./composables/usePrivateBotOwnerAuth', () => ({
  usePrivateBotOwnerAuth: () => authMocks,
}))
vi.mock('./components/QqccBotSettings.vue', () => ({ default: SettingsStub }))
vi.mock('ant-design-vue/es/message', () => ({ default: messageMocks }))

import PrivateBotOwnerApp from './PrivateBotOwnerApp.vue'

const ButtonStub = defineComponent({
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

const InputPasswordStub = defineComponent({
  props: ['value'],
  emits: ['update:value', 'pressEnter'],
  template: '<input type="password" :value="value" @input="$emit(\'update:value\', $event.target.value)" @keydown.enter="$emit(\'pressEnter\')" />',
})

const passthroughStub = (name: string) =>
  defineComponent({ name, template: '<div><slot /></div>' })

const ownerPayload = {
  bot: {
    id: 7,
    telegram_bot_id: 123456,
    telegram_username: 'alice_private_bot',
    telegram_display_name: 'Alice Bot',
    owner_enabled: true,
    admin_enabled: true,
    runtime_status: 'active',
    last_error_code: null,
    last_error_message: null,
    last_webhook_at: '2026-07-12T07:00:00Z',
    last_update_at: '2026-07-12T07:01:00Z',
    updated_at: '2026-07-12T07:02:00Z',
  },
  config: { global_enabled: true },
  config_version: 3,
  options: { video_engines: [] },
}

const mountOwnerApp = () =>
  mount(PrivateBotOwnerApp, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-input-password': InputPasswordStub,
        'a-spin': passthroughStub('SpinStub'),
        'a-alert': passthroughStub('AlertStub'),
        'a-tag': passthroughStub('TagStub'),
        KeyOutlined: passthroughStub('KeyOutlinedStub'),
        LogoutOutlined: passthroughStub('LogoutOutlinedStub'),
        PauseCircleOutlined: passthroughStub('PauseCircleOutlinedStub'),
        PlayCircleOutlined: passthroughStub('PlayCircleOutlinedStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        RobotOutlined: passthroughStub('RobotOutlinedStub'),
        SyncOutlined: passthroughStub('SyncOutlinedStub'),
      },
    },
  })

describe('PrivateBotOwnerApp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/')
    authMocks.getAuthToken.mockReturnValue(null)
    apiMocks.exchangePrivateBotOwnerTicket.mockResolvedValue({
      access_token: 'owner-jwt',
      token_type: 'bearer',
      expires_in: 43200,
    })
    apiMocks.fetchPrivateBotOwnerMe.mockResolvedValue(ownerPayload)
    apiMocks.updatePrivateBotOwnerConfig.mockResolvedValue({
      ...ownerPayload,
      config: { global_enabled: false },
      config_version: 4,
    })
    apiMocks.updatePrivateBotOwnerCredentials.mockResolvedValue(ownerPayload)
    apiMocks.pausePrivateBotOwner.mockResolvedValue({
      ...ownerPayload,
      bot: { ...ownerPayload.bot, owner_enabled: false, runtime_status: 'paused' },
    })
    apiMocks.resumePrivateBotOwner.mockResolvedValue(ownerPayload)
    apiMocks.retryPrivateBotOwner.mockResolvedValue(ownerPayload)
  })

  it('exchanges a one-time ticket, cleans it from the URL, and opens the owner console', async () => {
    window.history.replaceState({}, '', '/?from=telegram#ticket=one-time-ticket&view=manage')

    const wrapper = mountOwnerApp()
    expect(window.location.href).not.toContain('ticket=')
    expect(window.location.search).toBe('?from=telegram')
    await flushPromises()

    expect(apiMocks.exchangePrivateBotOwnerTicket).toHaveBeenCalledWith('one-time-ticket')
    expect(authMocks.setAuthToken).toHaveBeenCalledWith('owner-jwt')
    expect(apiMocks.fetchPrivateBotOwnerMe).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('@alice_private_bot')
    expect(wrapper.findComponent(SettingsStub).exists()).toBe(true)
  })

  it('rejects a ticket supplied through the query string and removes it from the URL', async () => {
    window.history.replaceState({}, '', '/?ticket=query-ticket&from=external')

    const wrapper = mountOwnerApp()
    await flushPromises()

    expect(apiMocks.exchangePrivateBotOwnerTicket).not.toHaveBeenCalled()
    expect(apiMocks.fetchPrivateBotOwnerMe).not.toHaveBeenCalled()
    expect(window.location.search).toBe('?from=external')
    expect(wrapper.text()).toContain('需要新的管理链接')
  })

  it('saves tenant config with config_version and uses the tenant media uploader', async () => {
    authMocks.getAuthToken.mockReturnValue('existing-owner-jwt')
    const wrapper = mountOwnerApp()
    await flushPromises()

    const settings = wrapper.findComponent(SettingsStub)
    const saved = await settings.props('updateConfig')({ global_enabled: false })

    expect(apiMocks.updatePrivateBotOwnerConfig).toHaveBeenCalledWith({
      config_version: 3,
      config: { global_enabled: false },
    })
    expect(saved.config).toEqual({ global_enabled: false })
    expect(settings.props('uploadDemoMedia')).toBe(apiMocks.uploadPrivateBotOwnerDemoMedia)
    expect(settings.props('demoMediaObjectPrefixes')).toEqual([
      'qqcc/private/7/demo',
    ])
  })

  it('clears a replacement token from the input immediately after submission', async () => {
    authMocks.getAuthToken.mockReturnValue('existing-owner-jwt')
    const wrapper = mountOwnerApp()
    await flushPromises()

    const tokenInput = wrapper.get('[data-testid="owner-credential-token"]')
    await tokenInput.setValue('123456:AA-new-secret')
    await wrapper.get('[data-testid="owner-update-credentials"]').trigger('click')

    expect((tokenInput.element as HTMLInputElement).value).toBe('')
    await flushPromises()
    expect(apiMocks.updatePrivateBotOwnerCredentials).toHaveBeenCalledWith('123456:AA-new-secret')
  })

  it('allows a provisioning Bot to retry its Telegram connection', async () => {
    authMocks.getAuthToken.mockReturnValue('existing-owner-jwt')
    apiMocks.fetchPrivateBotOwnerMe.mockResolvedValue({
      ...ownerPayload,
      bot: { ...ownerPayload.bot, runtime_status: 'provisioning' },
    })

    const wrapper = mountOwnerApp()
    await flushPromises()

    expect(wrapper.get('[data-testid="owner-retry-bot"]').text()).toContain('重试接入')
  })

  it.each([
    {
      action: 'resume',
      selector: '[data-testid="owner-resume-bot"]',
      initialBot: { ...ownerPayload.bot, owner_enabled: false, runtime_status: 'paused' },
      requestMock: apiMocks.resumePrivateBotOwner,
    },
    {
      action: 'retry',
      selector: '[data-testid="owner-retry-bot"]',
      initialBot: { ...ownerPayload.bot, runtime_status: 'error' },
      requestMock: apiMocks.retryPrivateBotOwner,
    },
  ])('does not report $action success when a 2xx response remains in error', async ({ selector, initialBot, requestMock }) => {
    authMocks.getAuthToken.mockReturnValue('existing-owner-jwt')
    const initialPayload = { ...ownerPayload, bot: initialBot }
    const errorPayload = {
      ...ownerPayload,
      bot: {
        ...ownerPayload.bot,
        runtime_status: 'error',
        last_error_code: 'webhook_registration_failed',
        last_error_message: 'Telegram webhook registration failed',
      },
    }
    apiMocks.fetchPrivateBotOwnerMe
      .mockResolvedValueOnce(initialPayload)
      .mockResolvedValueOnce(errorPayload)
    requestMock.mockResolvedValueOnce(errorPayload)

    const wrapper = mountOwnerApp()
    await flushPromises()
    await wrapper.get(selector).trigger('click')
    await flushPromises()

    expect(requestMock).toHaveBeenCalledOnce()
    expect(apiMocks.fetchPrivateBotOwnerMe).toHaveBeenCalledTimes(2)
    expect(messageMocks.success).not.toHaveBeenCalled()
    expect(messageMocks.error).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('接入异常')
  })

  it('warns instead of reporting token rotation success when Telegram activation fails', async () => {
    authMocks.getAuthToken.mockReturnValue('existing-owner-jwt')
    const errorPayload = {
      ...ownerPayload,
      bot: {
        ...ownerPayload.bot,
        runtime_status: 'error',
        last_error_code: 'webhook_registration_failed',
      },
    }
    apiMocks.updatePrivateBotOwnerCredentials.mockResolvedValue(errorPayload)
    apiMocks.fetchPrivateBotOwnerMe
      .mockResolvedValueOnce(ownerPayload)
      .mockResolvedValueOnce(errorPayload)

    const wrapper = mountOwnerApp()
    await flushPromises()
    await wrapper.get('[data-testid="owner-credential-token"]').setValue('123456:AA-new-secret')
    await wrapper.get('[data-testid="owner-update-credentials"]').trigger('click')
    await flushPromises()

    expect(apiMocks.fetchPrivateBotOwnerMe).toHaveBeenCalledTimes(2)
    expect(messageMocks.success).not.toHaveBeenCalled()
    expect(messageMocks.warning).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('接入异常')
  })

  it('does not open without a ticket or an existing owner session', async () => {
    const wrapper = mountOwnerApp()
    await flushPromises()

    expect(apiMocks.exchangePrivateBotOwnerTicket).not.toHaveBeenCalled()
    expect(apiMocks.fetchPrivateBotOwnerMe).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('需要新的管理链接')
  })
})
