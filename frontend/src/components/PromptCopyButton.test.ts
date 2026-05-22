// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PromptCopyButton from '@/components/PromptCopyButton.vue'

describe('PromptCopyButton', () => {
  it('renders label in desktop mode and emits click', async () => {
    const wrapper = mount(PromptCopyButton, {
      props: {
        label: '复制提示词',
      },
    })

    expect(wrapper.text()).toContain('复制提示词')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('hides label in compact mode', () => {
    const wrapper = mount(PromptCopyButton, {
      props: {
        label: '复制提示词',
        compact: true,
      },
    })

    expect(wrapper.text()).not.toContain('复制提示词')
  })
})
