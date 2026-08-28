// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchNotificationCenterSettings: vi.fn(),
  updateNotificationCenterSettings: vi.fn(),
  fetchObserverReports: vi.fn(),
  fetchObserverNotificationLogs: vi.fn(),
}))

vi.mock('../api/notificationCenterApi', () => apiMocks)

import NotificationCenter from './NotificationCenter.vue'

describe('NotificationCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchNotificationCenterSettings.mockResolvedValue({
      admin_telegram_user_ids: [42],
      authorized_group_ids: [-1001],
      support_ticket_user_ids: [84],
      queue_alerts_enabled: true,
      queue_total_pending_threshold: 20,
      queue_type_pending_threshold: 10,
      group_collection_enabled: true,
      daily_reports_enabled: false,
      weekly_reports_enabled: false,
      monthly_reports_enabled: false,
    })
    apiMocks.updateNotificationCenterSettings.mockImplementation(async payload => payload)
    apiMocks.fetchObserverReports.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    apiMocks.fetchObserverNotificationLogs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  })

  it('loads and saves all Telegram recipient and authorized group settings', async () => {
    const wrapper = mount(NotificationCenter, { global: { stubs: { 'a-switch': true } } })
    await flushPromises()

    expect(wrapper.get('[data-testid="observer-admin-ids"]').element).toHaveProperty('value', '42')
    expect(wrapper.get('[data-testid="authorized-group-ids"]').element).toHaveProperty('value', '-1001')
    await wrapper.get('[data-testid="observer-admin-ids"]').setValue('42\n108')
    await wrapper.get('[data-testid="save-settings"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateNotificationCenterSettings).toHaveBeenCalledWith(
      expect.objectContaining({ admin_telegram_user_ids: [42, 108] }),
    )
  })

  it('has separate report and notification record views', async () => {
    const wrapper = mount(NotificationCenter, { global: { stubs: { 'a-switch': true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('报告记录')
    expect(wrapper.text()).toContain('通知记录')
  })

  it('loads and saves total and per-type queue thresholds', async () => {
    const wrapper = mount(NotificationCenter, { global: { stubs: { 'a-switch': true } } })
    await flushPromises()

    expect(wrapper.get('[data-testid="queue-total-threshold"]').element).toHaveProperty('value', '20')
    expect(wrapper.get('[data-testid="queue-type-threshold"]').element).toHaveProperty('value', '10')
    await wrapper.get('[data-testid="queue-total-threshold"]').setValue('30')
    await wrapper.get('[data-testid="queue-type-threshold"]').setValue('6')
    await wrapper.get('[data-testid="save-settings"]').trigger('click')
    await flushPromises()

    expect(apiMocks.updateNotificationCenterSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        queue_total_pending_threshold: 30,
        queue_type_pending_threshold: 6,
      }),
    )
  })
})
