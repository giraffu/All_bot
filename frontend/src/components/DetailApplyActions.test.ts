// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DetailApplyActions from '@/components/DetailApplyActions.vue'

describe('DetailApplyActions', () => {
  it('renders vertical copy/apply stack and emits actions', async () => {
    const wrapper = mount(DetailApplyActions, {
      props: {
        showCopy: true,
        copyLabel: '复制提示词',
        applyLabel: '一键应用',
        hintText: '提示文案',
      },
    })

    const buttons = wrapper.findAll('button')

    expect(wrapper.text()).toContain('复制提示词')
    expect(wrapper.text()).toContain('一键应用')
    expect(wrapper.text()).toContain('提示文案')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('copy')).toHaveLength(1)
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })

  it('renders compact apply-only mode without copy label', () => {
    const wrapper = mount(DetailApplyActions, {
      props: {
        inline: true,
        compactApply: true,
        applyLabel: '一键应用',
        hintText: '移动端不展示长提示',
      },
    })

    expect(wrapper.text()).toContain('一键应用')
    expect(wrapper.text()).not.toContain('复制提示词')
    expect(wrapper.text()).not.toContain('移动端不展示长提示')
  })
})
