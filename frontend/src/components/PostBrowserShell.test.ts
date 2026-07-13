// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PostBrowserShell from '@/components/PostBrowserShell.vue'

describe('PostBrowserShell', () => {
  it('renders header and content slots while delegating state to the shared block', async () => {
    const wrapper = mount(PostBrowserShell, {
      props: {
        errorText: '加载失败',
        showRetry: true,
        retryText: '重试加载',
      },
      slots: {
        header: '<div class="header-slot">header</div>',
        default: '<div class="content-slot">content</div>',
      },
    })

    expect(wrapper.find('.header-slot').exists()).toBe(true)
    expect(wrapper.find('.content-slot').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载失败')

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
