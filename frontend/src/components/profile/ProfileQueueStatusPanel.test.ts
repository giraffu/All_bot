// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import ProfileQueueStatusPanel from '@/components/profile/ProfileQueueStatusPanel.vue'

describe('ProfileQueueStatusPanel', () => {
  it('shows running status when queued tasks exist even if worker heartbeat is offline', () => {
    const wrapper = mount(ProfileQueueStatusPanel, {
      props: {
        queueStatus: {
          loading: false,
          isFirstLoad: false,
          data: {
            comfy_online: false,
            queue_size: 1,
            queue_by_type: {
              i2i_pro: 1,
            },
          },
        },
        resolveQueueTaskTypeLabel: (type: string | number) => String(type),
        fetchQueueStatus: vi.fn(),
      },
      global: {
        plugins: [i18n],
      },
    })

    const text = wrapper.text()
    expect(text).toContain('运行中')
    expect(text).not.toContain('休息中')
    expect(text).toContain('1 个')
  })
})
