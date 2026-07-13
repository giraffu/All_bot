// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'

describe('PostCardMetricsBar', () => {
  it('renders counts and emits interaction events', async () => {
    const wrapper = mount(PostCardMetricsBar, {
      props: {
        likesCount: 3,
        dislikesCount: 1,
        appliedCount: 8,
        commentsCount: 2,
        hasLiked: true,
        showComments: true,
      },
    })

    const buttons = wrapper.findAll('button')

    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('2')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')

    expect(wrapper.emitted('like')).toHaveLength(1)
    expect(wrapper.emitted('dislike')).toHaveLength(1)
    expect(wrapper.emitted('comment')).toHaveLength(1)
  })
})
