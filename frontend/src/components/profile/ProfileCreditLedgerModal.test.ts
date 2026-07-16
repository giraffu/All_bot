// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import i18n from '@/i18n'
import ProfileCreditLedgerModal from '@/components/profile/ProfileCreditLedgerModal.vue'

const { getCurrentUserCreditLedgerMock } = vi.hoisted(() => ({
  getCurrentUserCreditLedgerMock: vi.fn(),
}))

vi.mock('@/api/creditLedger', () => ({
  getCurrentUserCreditLedger: getCurrentUserCreditLedgerMock,
}))

vi.mock('@/composables/useViewport', async () => {
  const { ref } = await vi.importActual<typeof import('vue')>('vue')
  return {
    useViewport: () => ({
      isMobile: ref(false),
    }),
  }
})

const modalStub = defineComponent({
  name: 'AModalStub',
  props: {
    open: Boolean,
  },
  emits: ['update:open'],
  template: '<div v-if="open"><slot /></div>',
})

const spinStub = defineComponent({
  name: 'ASpinStub',
  template: '<div><slot /></div>',
})

const buttonStub = defineComponent({
  name: 'AButtonStub',
  props: {
    loading: Boolean,
  },
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
})

function mountModal() {
  return mount(ProfileCreditLedgerModal, {
    props: {
      open: true,
    },
    global: {
      plugins: [i18n],
      stubs: {
        'a-modal': modalStub,
        'a-spin': spinStub,
        'a-button': buttonStub,
      },
      renderStubDefaultSlot: true,
    },
  })
}

describe('ProfileCreditLedgerModal', () => {
  beforeEach(() => {
    getCurrentUserCreditLedgerMock.mockReset()
  })

  it('loads five ledger entries per page and switches pages', async () => {
    getCurrentUserCreditLedgerMock
      .mockResolvedValueOnce({
        items: [
          {
            id: 1,
            operation_type: 'checkin',
            display_key: 'credit_ledger.operation_types.checkin',
            direction: 'income',
            credit_change: 10,
            current_balance: 110,
            created_at: '2026-07-03T12:00:00',
            display_context: { reward: 10 },
          },
        ],
        total: 8,
        page: 1,
        page_size: 5,
        total_pages: 2,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 2,
            operation_type: 'txt2img',
            display_key: 'task_type.txt2img',
            direction: 'expense',
            credit_change: -2,
            current_balance: 108,
            created_at: '2026-07-03T12:05:00',
            display_context: {},
          },
        ],
        total: 8,
        page: 2,
        page_size: 5,
        total_pages: 2,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 1,
            operation_type: 'checkin',
            display_key: 'credit_ledger.operation_types.checkin',
            direction: 'income',
            credit_change: 10,
            current_balance: 110,
            created_at: '2026-07-03T12:00:00',
            display_context: { reward: 10 },
          },
        ],
        total: 8,
        page: 1,
        page_size: 5,
        total_pages: 2,
      })

    const wrapper = mountModal()
    await flushPromises()

    expect(getCurrentUserCreditLedgerMock).toHaveBeenCalledWith({
      page: 1,
      page_size: 5,
    })
    expect(wrapper.text()).toContain('签到奖励')
    expect(wrapper.text()).toContain('收入')
    expect(wrapper.text()).toContain('+10')
    expect(wrapper.text()).toContain('余额 110')
    expect(wrapper.text()).toContain('奖励 10')
    expect(wrapper.find('.profile-credit-ledger-modal__amount--income').exists()).toBe(true)
    expect(wrapper.find('[data-testid="credit-ledger-load-more"]').exists()).toBe(false)

    await wrapper.find('button[aria-label="下一页"]').trigger('click')
    await flushPromises()

    expect(getCurrentUserCreditLedgerMock).toHaveBeenLastCalledWith({
      page: 2,
      page_size: 5,
    })
    expect(wrapper.find('[data-testid="credit-ledger-item-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="credit-ledger-item-2"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('文生图')
    expect(wrapper.text()).toContain('支出')
    expect(wrapper.text()).toContain('-2')
    expect(wrapper.find('.profile-credit-ledger-modal__amount--expense').exists()).toBe(true)

    await wrapper.find('button[aria-label="上一页"]').trigger('click')
    await flushPromises()

    expect(getCurrentUserCreditLedgerMock).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 5,
    })
    expect(wrapper.find('[data-testid="credit-ledger-item-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="credit-ledger-item-2"]').exists()).toBe(false)
  })

  it('renders the empty state when there are no ledger entries', async () => {
    getCurrentUserCreditLedgerMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 5,
      total_pages: 0,
    })

    const wrapper = mountModal()
    await flushPromises()

    expect(wrapper.find('[data-testid="credit-ledger-empty"]').text()).toContain(
      '暂无灵石收支记录',
    )
  })

  it('renders an error state and retries loading', async () => {
    getCurrentUserCreditLedgerMock
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({
        items: [],
        total: 0,
        page: 1,
        page_size: 5,
        total_pages: 0,
      })

    const wrapper = mountModal()
    await flushPromises()

    expect(wrapper.text()).toContain('加载灵石账本失败')

    await wrapper.find('[data-testid="credit-ledger-retry"]').trigger('click')
    await flushPromises()

    expect(getCurrentUserCreditLedgerMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('暂无灵石收支记录')
  })
})
