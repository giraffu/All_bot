// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'

describe('GenerationWorkbenchShell', () => {
  it('renders shared workbench layout with forwarded slots and custom classes', () => {
    const wrapper = mount(GenerationWorkbenchShell, {
      props: {
        title: '工作台标题',
        description: '工作台描述',
        containerClass: 'custom-container',
        innerClass: 'custom-inner',
        leftPanelClass: 'custom-left-panel',
        leftBodyClass: 'custom-left-body',
        rightPanelClass: 'custom-right-panel',
      },
      slots: {
        'left-top': '<div class="left-top-slot">left-top</div>',
        'left-content': '<div class="left-content-slot">left-content</div>',
        'left-footer': '<div class="left-footer-slot">left-footer</div>',
        'right-panel': '<div class="right-panel-slot">right-panel</div>',
      },
    })

    expect(wrapper.find('.custom-container').exists()).toBe(true)
    expect(wrapper.find('.custom-inner').exists()).toBe(true)
    expect(wrapper.find('.custom-left-panel').exists()).toBe(true)
    expect(wrapper.find('.custom-left-body').exists()).toBe(true)
    expect(wrapper.find('.custom-right-panel').exists()).toBe(true)
    expect(wrapper.find('.left-top-slot').exists()).toBe(true)
    expect(wrapper.find('.left-content-slot').exists()).toBe(true)
    expect(wrapper.find('.left-footer-slot').exists()).toBe(true)
    expect(wrapper.find('.right-panel-slot').exists()).toBe(true)
    expect(wrapper.text()).toContain('工作台标题')
    expect(wrapper.text()).toContain('工作台描述')
  })
})
