// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchAlipayDirectRoster: vi.fn(),
  bulkUpdateAlipayDirectRoster: vi.fn(),
}))
const confirmMock = vi.hoisted(() => vi.fn())

vi.mock('../api/alipayDirectRosterApi', () => apiMocks)
vi.mock('ant-design-vue', () => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
  Modal: {
    confirm: confirmMock,
  },
}))

const AlipayDirectRoster = await import('./AlipayDirectRoster.vue').then(
  module => module.default,
)

const PassthroughStub = defineComponent({
  template: '<div><slot /><slot name="extra" /></div>',
})

const ButtonStub = defineComponent({
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
})

const CheckboxStub = defineComponent({
  props: ['checked'],
  emits: ['update:checked', 'change'],
  template: `
    <label>
      <input
        class="checkbox-input"
        type="checkbox"
        :checked="checked"
        @change="$emit('update:checked', $event.target.checked); $emit('change', $event)"
      >
      <slot />
    </label>
  `,
})

const TableStub = defineComponent({
  props: ['dataSource', 'rowSelection', 'pagination'],
  emits: ['change'],
  template: `
    <div class="table-stub">
      <button
        class="next-page"
        type="button"
        @click="$emit('change', { current: 2, pageSize: 20 }, {}, {})"
      >
        下一页
      </button>
      <button
        v-for="record in dataSource"
        :key="record.id"
        class="select-row"
        type="button"
        @click="rowSelection.onChange([record.id])"
      >
        {{ record.full_name }}
      </button>
    </div>
  `,
})

const mountRoster = () => mount(AlipayDirectRoster, {
  global: {
    stubs: {
      'a-card': PassthroughStub,
      'a-form': PassthroughStub,
      'a-form-item': PassthroughStub,
      'a-row': PassthroughStub,
      'a-col': PassthroughStub,
      'a-select': PassthroughStub,
      'a-select-option': PassthroughStub,
      'a-input-number': PassthroughStub,
      'a-range-picker': PassthroughStub,
      'a-input-search': PassthroughStub,
      'a-space': PassthroughStub,
      'a-statistic': PassthroughStub,
      'a-alert': PassthroughStub,
      'a-tag': PassthroughStub,
      'a-button': ButtonStub,
      'a-checkbox': CheckboxStub,
      'a-table': TableStub,
    },
  },
})

describe('AlipayDirectRoster', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchAlipayDirectRoster.mockResolvedValue({
      items: [
        {
          id: 1001,
          username: 'repeat_buyer',
          full_name: 'Repeat Buyer',
          created_at: '2026-02-05T08:30:00',
          alipay_direct_enabled: true,
          paid_count: 6,
          direct_paid_count: 2,
          has_direct_paid: true,
          last_direct_paid_at: '2026-08-20T12:00:00',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    apiMocks.bulkUpdateAlipayDirectRoster.mockResolvedValue({
      status: 'ok',
      matched_count: 1,
      updated_count: 1,
      enabled: false,
    })
    confirmMock.mockImplementation(options => options.onOk())
  })

  it('defaults to enabled users and submits explicit checked rows', async () => {
    const wrapper = mountRoster()
    await flushPromises()

    expect(apiMocks.fetchAlipayDirectRoster).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, pageSize: 20, enabled: true }),
    )
    expect(wrapper.text()).toContain('Repeat Buyer')
    await wrapper.get('.select-row').trigger('click')
    const cancelButton = wrapper.findAll('button').find(button =>
      button.text().includes('批量取消直连'),
    )
    await cancelButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.bulkUpdateAlipayDirectRoster).toHaveBeenCalledWith({
      enabled: false,
      selection_mode: 'ids',
      user_ids: [1001],
    })
  })

  it('selects every filtered page with a filter selection payload', async () => {
    const wrapper = mountRoster()
    await flushPromises()

    await wrapper.get('.select-all-matching .checkbox-input').setValue(true)
    await wrapper.get('.next-page').trigger('click')
    await flushPromises()
    const enableButton = wrapper.findAll('button').find(button =>
      button.text().includes('批量设为直连'),
    )
    await enableButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.bulkUpdateAlipayDirectRoster).toHaveBeenCalledWith({
      enabled: true,
      selection_mode: 'filters',
      filters: expect.objectContaining({ enabled: true }),
    })
  })
})
