// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchPlans: vi.fn(),
  fetchOrders: vi.fn(),
}))

vi.mock('../api/api', () => ({
  fetchPlans: apiMocks.fetchPlans,
  fetchOrders: apiMocks.fetchOrders,
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  deletePlan: vi.fn(),
}))

vi.mock('ant-design-vue/es/message', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}))

const InputStub = defineComponent({
  name: 'AInput',
  props: ['value', 'placeholder'],
  emits: ['update:value', 'pressEnter', 'clear'],
  template: '<input :aria-label="placeholder" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
})

const ButtonStub = defineComponent({
  name: 'AButton',
  template: '<button type="button"><slot /></button>',
})

const PassThroughStub = defineComponent({
  template: '<div><slot /></div>',
})

const RechargeSystem = await import('./RechargeSystem.vue').then(module => module.default)

describe('RechargeSystem order browsing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchPlans.mockResolvedValue([])
    apiMocks.fetchOrders.mockResolvedValue({ items: [], total: 0 })
  })

  it('submits the internal user id from a reachable filter form', async () => {
    const wrapper = mount(RechargeSystem, {
      global: {
        stubs: {
          AInput: InputStub,
          AButton: ButtonStub,
          ASelect: PassThroughStub,
          ASelectOption: PassThroughStub,
          ATabs: PassThroughStub,
          ATabPane: PassThroughStub,
          ATable: PassThroughStub,
          ATag: PassThroughStub,
          AModal: PassThroughStub,
          AForm: PassThroughStub,
          AFormItem: PassThroughStub,
          AInputNumber: PassThroughStub,
          ASwitch: PassThroughStub,
          APopconfirm: PassThroughStub,
        },
      },
    })
    await flushPromises()

    await wrapper.get('input[aria-label="搜索内部用户ID"]').setValue('6494421613')
    expect(wrapper.get('[data-testid="order-filter-submit"]').text()).toBe('查询/刷新')
    await wrapper.get('[data-testid="order-filters"]').trigger('submit')
    await flushPromises()

    expect(apiMocks.fetchOrders).toHaveBeenLastCalledWith(
      1,
      10,
      'ALL',
      null,
      '6494421613',
      null,
    )
    expect(wrapper.get('[data-testid="order-filters"]').classes()).toContain('order-filters')
    expect(wrapper.get('[data-testid="orders-table"]').attributes('data-scroll-x')).toBe('980')
  })

  it('shows the persisted RMB payment provider', async () => {
    apiMocks.fetchOrders.mockResolvedValue({
      items: [
        {
          id: 1,
          order_id: 'ORDER-1',
          payment_provider: 'ALIPAY_DIRECT',
          payment_channel: 'RMB',
          final_price: 0.01,
          status: 'PENDING',
        },
      ],
      total: 1,
    })
    const TableWithCells = defineComponent({
      props: ['columns', 'dataSource'],
      template: `
        <div>
          <div v-for="record in dataSource" :key="record.id">
            <div v-for="column in columns" :key="column.key">
              <slot name="bodyCell" :column="column" :record="record">
                {{ column.dataIndex ? record[column.dataIndex] : '' }}
              </slot>
            </div>
          </div>
        </div>
      `,
    })
    const wrapper = mount(RechargeSystem, {
      global: {
        stubs: {
          AInput: InputStub,
          AButton: ButtonStub,
          ASelect: PassThroughStub,
          ASelectOption: PassThroughStub,
          ATabs: PassThroughStub,
          ATabPane: PassThroughStub,
          ATable: TableWithCells,
          ATag: PassThroughStub,
          AModal: PassThroughStub,
          AForm: PassThroughStub,
          AFormItem: PassThroughStub,
          AInputNumber: PassThroughStub,
          ASwitch: PassThroughStub,
          APopconfirm: PassThroughStub,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('支付宝直连')
  })
})
