// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TemplateApplyButton from '@/components/TemplateApplyButton.vue'

describe('TemplateApplyButton', () => {
  it('renders loading label and emits click when idle', async () => {
    const wrapper = mount(TemplateApplyButton, {
      props: {
        label: '一键应用',
        loadingLabel: '提取中',
      },
    })

    expect(wrapper.text()).toContain('一键应用')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)

    await wrapper.setProps({ loading: true })
    expect(wrapper.text()).toContain('提取中')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
})
