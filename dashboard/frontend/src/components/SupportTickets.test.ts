// @vitest-environment jsdom

import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchSupportTickets: vi.fn(),
  fetchSupportTicket: vi.fn(),
  updateSupportTicket: vi.fn(),
  replySupportTicket: vi.fn(),
}))

vi.mock('../api/api', () => apiMocks)

import SupportTickets from './SupportTickets.vue'

const ListStub = defineComponent({
  props: ['dataSource'],
  setup(props, { slots }) {
    return () =>
      h(
        'div',
        (props.dataSource ?? []).map((item: unknown, index: number) =>
          slots.renderItem?.({ item, index }),
        ),
      )
  },
})

const passthroughStub = (name: string) =>
  defineComponent({
    name,
    template: '<div><slot /></div>',
  })

describe('SupportTickets', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchSupportTickets.mockResolvedValue({
      items: [
        {
          id: 42,
          category: 'recharge',
          status: 'open',
          full_name: '测试用户',
          last_message_at: '2026-07-22T14:20:00Z',
        },
      ],
      total: 1,
    })
  })

  it('renders ticket fields from the list render-item slot payload', async () => {
    const wrapper = mount(SupportTickets, {
      global: {
        stubs: {
          'a-list': ListStub,
          'a-list-item': passthroughStub('ListItemStub'),
          'a-spin': passthroughStub('SpinStub'),
          'a-select': passthroughStub('SelectStub'),
          'a-button': passthroughStub('ButtonStub'),
          'a-tag': passthroughStub('TagStub'),
          'a-textarea': passthroughStub('TextareaStub'),
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('#42 充值问题')
    expect(wrapper.text()).toContain('测试用户')
    expect(wrapper.text()).toContain('open')
  })
})
