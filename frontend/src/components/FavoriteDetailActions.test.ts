// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import FavoriteDetailActions from '@/components/FavoriteDetailActions.vue'

describe('FavoriteDetailActions', () => {
  it('renders desktop actions and emits unfavorite/comment', async () => {
    const wrapper = mount(FavoriteDetailActions, {
      props: {
        commentsCount: 7,
        unfavoriteLabel: '取消收藏',
      },
    })

    expect(wrapper.text()).toContain('取消收藏')
    expect(wrapper.text()).toContain('7')

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('unfavorite')).toHaveLength(1)
    expect(wrapper.emitted('comment')).toHaveLength(1)
  })

  it('renders compact actions', () => {
    const wrapper = mount(FavoriteDetailActions, {
      props: {
        compact: true,
        commentsCount: 3,
        unfavoriteLabel: '取消收藏',
      },
    })

    expect(wrapper.text()).toContain('取消收藏')
    expect(wrapper.text()).toContain('3')
  })
})
