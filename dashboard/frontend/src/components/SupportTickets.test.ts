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

const SelectStub = defineComponent({
  name: 'SelectStub',
  props: ['options'],
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
          'a-select': SelectStub,
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

  it('shows business tickets completely and exposes business in the category filter', async () => {
    apiMocks.fetchSupportTickets.mockResolvedValue({
      items: [
        {
          id: 5,
          category: 'business',
          status: 'open',
          username: 'giraffe',
          last_message_at: '2026-07-23T20:04:56Z',
        },
      ],
      total: 1,
    })
    const wrapper = mount(SupportTickets, {
      global: {
        stubs: {
          'a-list': ListStub,
          'a-list-item': passthroughStub('ListItemStub'),
          'a-spin': passthroughStub('SpinStub'),
          'a-select': SelectStub,
          'a-button': passthroughStub('ButtonStub'),
          'a-tag': passthroughStub('TagStub'),
          'a-textarea': passthroughStub('TextareaStub'),
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('#5 商业合作')
    const categoryOptions = wrapper.findAllComponents(SelectStub)[1].props('options')
    expect(categoryOptions).toContainEqual({ value: 'business', label: '商业合作' })
  })

  it('never renders an empty ticket heading for a future category', async () => {
    apiMocks.fetchSupportTickets.mockResolvedValue({
      items: [
        {
          id: 9,
          category: 'partner',
          status: 'open',
          username: 'giraffe',
          last_message_at: '2026-07-23T20:04:56Z',
        },
      ],
      total: 1,
    })
    const wrapper = mount(SupportTickets, {
      global: {
        stubs: {
          'a-list': ListStub,
          'a-list-item': passthroughStub('ListItemStub'),
          'a-spin': passthroughStub('SpinStub'),
          'a-select': SelectStub,
          'a-button': passthroughStub('ButtonStub'),
          'a-tag': passthroughStub('TagStub'),
          'a-textarea': passthroughStub('TextareaStub'),
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('#9 其他分类（partner）')
  })

  it('renders received image attachments as authenticated previews', async () => {
    apiMocks.fetchSupportTicket.mockResolvedValue({
      id: 42,
      category: 'business',
      status: 'open',
      telegram_user_id: 123,
      last_message_at: '2026-07-22T14:20:00Z',
      messages: [
        {
          id: 7,
          sender_type: 'user',
          attachments: [
            {
              filename: 'proposal.png',
              mime_type: 'image/png',
              url: '/api/support-tickets/attachments/proposal',
            },
          ],
          created_at: '2026-07-22T14:21:00Z',
        },
      ],
    })
    const wrapper = mount(SupportTickets, {
      global: {
        stubs: {
          'a-list': ListStub,
          'a-list-item': passthroughStub('ListItemStub'),
          'a-spin': passthroughStub('SpinStub'),
          'a-select': SelectStub,
          'a-button': passthroughStub('ButtonStub'),
          'a-tag': passthroughStub('TagStub'),
          'a-textarea': passthroughStub('TextareaStub'),
        },
      },
    })

    await flushPromises()
    await wrapper.find('.ticket-item').trigger('click')
    await flushPromises()

    const image = wrapper.get('img.attachment-image')
    expect(image.attributes('src')).toBe('/api/support-tickets/attachments/proposal')
    expect(image.attributes('alt')).toBe('proposal.png')
    expect(wrapper.text()).toContain('商业合作')
  })
})
