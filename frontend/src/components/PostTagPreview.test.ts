// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PostTagPreview from '@/components/PostTagPreview.vue'

describe('PostTagPreview', () => {
  it('renders formatted tags and overflow marker', () => {
    const wrapper = mount(PostTagPreview, {
      props: {
        tags: ['a', 'b', 'c'],
        maxVisible: 2,
        formatTag: (tag: string) => `tag:${tag}`,
      },
    })

    expect(wrapper.text()).toContain('tag:a')
    expect(wrapper.text()).toContain('tag:b')
    expect(wrapper.text()).not.toContain('tag:c')
    expect(wrapper.text()).toContain('...')
  })
})
