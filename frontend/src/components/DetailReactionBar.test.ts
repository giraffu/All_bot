// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DetailReactionBar from '@/components/DetailReactionBar.vue'

describe('DetailReactionBar', () => {
  it('renders desktop actions and emits like/dislike/comment', async () => {
    const wrapper = mount(DetailReactionBar, {
      props: {
        likesCount: 3,
        dislikesCount: 1,
        commentsCount: 5,
        hasLiked: true,
      },
    })

    const buttons = wrapper.findAll('button')

    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('5')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')

    expect(wrapper.emitted('like')).toHaveLength(1)
    expect(wrapper.emitted('dislike')).toHaveLength(1)
    expect(wrapper.emitted('comment')).toHaveLength(1)
  })
})
