// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SubmissionManageButtons from '@/components/SubmissionManageButtons.vue'

describe('SubmissionManageButtons', () => {
  it('renders active labels and emits toggle/delete', async () => {
    const wrapper = mount(SubmissionManageButtons, {
      props: {
        isActive: true,
        onShelfLabel: '上架',
        offShelfLabel: '下架',
        deleteLabel: '删除',
      },
    })

    expect(wrapper.text()).toContain('下架')
    expect(wrapper.text()).toContain('删除')

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('toggle')).toHaveLength(1)
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })

  it('renders compact mode with inactive label', () => {
    const wrapper = mount(SubmissionManageButtons, {
      props: {
        compact: true,
        isActive: false,
        onShelfLabel: '上架',
        offShelfLabel: '下架',
        deleteLabel: '删除',
      },
    })

    expect(wrapper.text()).toContain('上架')
  })
})
