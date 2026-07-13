// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ListStateBlock from '@/components/ListStateBlock.vue'

describe('ListStateBlock', () => {
  it('renders loading spinner when loading', () => {
    const wrapper = mount(ListStateBlock, {
      props: {
        loading: true,
        empty: true,
        emptyText: '暂无数据',
      },
    })

    expect(wrapper.find('.animate-spin').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('暂无数据')
  })

  it('renders empty text when empty and not loading', () => {
    const wrapper = mount(ListStateBlock, {
      props: {
        loading: false,
        empty: true,
        emptyText: '暂无数据',
      },
    })

    expect(wrapper.text()).toContain('暂无数据')
  })

  it('renders retry button and emits retry on error', async () => {
    const wrapper = mount(ListStateBlock, {
      props: {
        errorText: '加载失败',
        showRetry: true,
        retryText: '重试加载',
      },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
