// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchPrivateBotsAdmin: vi.fn(),
  fetchPrivateBotAdminDetail: vi.fn(),
  disablePrivateBotAdmin: vi.fn(),
  enablePrivateBotAdmin: vi.fn(),
  deletePrivateBotAdmin: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('../api/qqccConfigApi', () => apiMocks)
vi.mock('ant-design-vue/es/message', () => ({ default: messageMocks }))

import PrivateBotAdminManager from './PrivateBotAdminManager.vue'

const ButtonStub = defineComponent({
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
})

const InputStub = defineComponent({
  props: ['value', 'placeholder'],
  emits: ['update:value', 'pressEnter'],
  template: '<input :value="value" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" @keydown.enter="$emit(\'pressEnter\')" />',
})

const SelectStub = defineComponent({
  props: ['value'],
  emits: ['update:value'],
  template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value || undefined)"><slot /></select>',
})

const ModalStub = defineComponent({
  props: ['open'],
  emits: ['update:open'],
  template: '<div v-if="open" class="modal-stub"><slot /></div>',
})

const PopconfirmStub = defineComponent({
  emits: ['confirm'],
  template: '<span class="popconfirm-stub"><slot /><button type="button" class="confirm-action" @click="$emit(\'confirm\')">confirm</button></span>',
})

const passthroughStub = (name: string) =>
  defineComponent({ name, template: '<div><slot /></div>' })

const botItem = {
  id: 7,
  owner: { id: 12, telegram_id: 9988, username: 'alice', full_name: 'Alice' },
  telegram_bot_id: 123456,
  telegram_username: 'alice_private_bot',
  telegram_display_name: 'Alice Bot',
  token_fingerprint_hint: 'sha256:…9af2',
  owner_enabled: true,
  admin_enabled: true,
  runtime_status: 'active',
  last_error_code: null,
  last_error_message: null,
  last_webhook_at: '2026-07-12T07:00:00Z',
  last_update_at: '2026-07-12T07:01:00Z',
  created_at: '2026-07-12T06:00:00Z',
  updated_at: '2026-07-12T07:02:00Z',
}

const detailItem = {
  ...botItem,
  config: { global_enabled: true, main_buttons: { ai_draw: true } },
  config_version: 4,
  options: { video_engines: [] },
  audit_logs: [
    {
      id: 1,
      actor_type: 'owner',
      actor_identifier: '12',
      action: 'config_saved',
      before_status: 'active',
      after_status: 'active',
      details: { config_version: 4 },
      created_at: '2026-07-12T07:02:00Z',
    },
  ],
}

const mountManager = () =>
  mount(PrivateBotAdminManager, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': SelectStub,
        'a-select-option': defineComponent({ props: ['value'], template: '<option :value="value"><slot /></option>' }),
        'a-spin': passthroughStub('SpinStub'),
        'a-tag': passthroughStub('TagStub'),
        'a-empty': passthroughStub('EmptyStub'),
        'a-pagination': passthroughStub('PaginationStub'),
        'a-modal': ModalStub,
        'a-popconfirm': PopconfirmStub,
        'a-alert': passthroughStub('AlertStub'),
        DeleteOutlined: passthroughStub('DeleteOutlinedStub'),
        EyeOutlined: passthroughStub('EyeOutlinedStub'),
        ReloadOutlined: passthroughStub('ReloadOutlinedStub'),
        SafetyCertificateOutlined: passthroughStub('SafetyCertificateOutlinedStub'),
        StopOutlined: passthroughStub('StopOutlinedStub'),
      },
    },
  })

describe('PrivateBotAdminManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchPrivateBotsAdmin.mockResolvedValue({
      items: [botItem],
      total: 1,
      page: 1,
      page_size: 20,
    })
    apiMocks.fetchPrivateBotAdminDetail.mockResolvedValue(detailItem)
    apiMocks.disablePrivateBotAdmin.mockResolvedValue({
      bot: { ...botItem, admin_enabled: false, runtime_status: 'disabled' },
      config: detailItem.config,
      config_version: detailItem.config_version,
      options: detailItem.options,
    })
    apiMocks.enablePrivateBotAdmin.mockResolvedValue({
      bot: botItem,
      config: detailItem.config,
      config_version: detailItem.config_version,
      options: detailItem.options,
    })
    apiMocks.deletePrivateBotAdmin.mockResolvedValue({ ok: true })
  })

  it('loads and filters private Bots by owner, username, and runtime status', async () => {
    const wrapper = mountManager()
    await flushPromises()

    expect(apiMocks.fetchPrivateBotsAdmin).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      status: undefined,
      admin_enabled: undefined,
      owner: undefined,
      username: undefined,
    })
    expect(wrapper.text()).toContain('@alice_private_bot')
    expect(wrapper.text()).toContain('Alice')

    await wrapper.get('[data-testid="private-bot-owner-filter"]').setValue('alice')
    await wrapper.get('[data-testid="private-bot-username-filter"]').setValue('@render_bot')
    await wrapper.get('[data-testid="private-bot-status-filter"]').setValue('error')
    await wrapper.get('[data-testid="private-bot-admin-state-filter"]').setValue('disabled')
    await wrapper.get('[data-testid="private-bot-search"]').trigger('click')
    await flushPromises()

    expect(apiMocks.fetchPrivateBotsAdmin).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      status: 'error',
      admin_enabled: false,
      owner: 'alice',
      username: 'render_bot',
    })
  })

  it('shows masked credentials, health, audit logs, and a read-only config', async () => {
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.get('.private-bot-admin__bot-link').trigger('click')
    await flushPromises()

    expect(apiMocks.fetchPrivateBotAdminDetail).toHaveBeenCalledWith(7)
    expect(wrapper.get('[data-testid="private-bot-detail"]').text()).toContain('sha256:…9af2')
    expect(wrapper.get('[data-testid="private-bot-detail"]').text()).toContain('config_saved')
    expect(wrapper.get('[data-testid="private-bot-config-readonly"]').text()).toContain('global_enabled')
    expect(wrapper.text()).not.toContain('123456:AA-secret-token')
  })

  it('requires confirmation before disabling and permanently unbinding a Bot', async () => {
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.find('.popconfirm-stub .confirm-action').trigger('click')
    await flushPromises()

    expect(apiMocks.disablePrivateBotAdmin).toHaveBeenCalledWith(7)
    expect(messageMocks.success).toHaveBeenCalledWith('私有 Bot 已禁用')

    await wrapper.get('.private-bot-admin__bot-link').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="private-bot-delete"]').element.closest('.popconfirm-stub')
      ?.querySelector<HTMLButtonElement>('.confirm-action')?.click()
    await flushPromises()

    expect(apiMocks.deletePrivateBotAdmin).toHaveBeenCalledWith(7)
    expect(messageMocks.success).toHaveBeenCalledWith('私有 Bot 已永久解绑')
  })

  it('does not report admin restore success when the 2xx response remains in error', async () => {
    const disabledBot = {
      ...botItem,
      admin_enabled: false,
      runtime_status: 'disabled',
    }
    const errorBot = {
      ...botItem,
      runtime_status: 'error',
      last_error_code: 'webhook_registration_failed',
      last_error_message: 'Telegram webhook registration failed',
    }
    apiMocks.fetchPrivateBotsAdmin
      .mockResolvedValueOnce({ items: [disabledBot], total: 1, page: 1, page_size: 20 })
      .mockResolvedValueOnce({ items: [errorBot], total: 1, page: 1, page_size: 20 })
    apiMocks.enablePrivateBotAdmin.mockResolvedValue({
      bot: errorBot,
      config: detailItem.config,
      config_version: detailItem.config_version,
      options: detailItem.options,
    })

    const wrapper = mountManager()
    await flushPromises()
    await wrapper.get('.popconfirm-stub .confirm-action').trigger('click')
    await flushPromises()

    expect(apiMocks.enablePrivateBotAdmin).toHaveBeenCalledWith(7)
    expect(apiMocks.fetchPrivateBotsAdmin).toHaveBeenCalledTimes(2)
    expect(messageMocks.success).not.toHaveBeenCalled()
    expect(messageMocks.error).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="private-bot-row-7"]').text()).toContain('异常')
  })
})
