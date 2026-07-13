// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DetailModalShell from '@/components/DetailModalShell.vue'

describe('DetailModalShell', () => {
  it('renders shared slots and emits close from both mobile and desktop entries', async () => {
    const wrapper = mount(DetailModalShell, {
      props: {
        infoContentClass: 'custom-info-content',
        desktopCloseButtonClass: 'custom-desktop-close',
      },
      slots: {
        'mobile-header': '<div class="mobile-header-slot">header</div>',
        media: '<div class="media-slot">media</div>',
        info: '<div class="info-slot">info</div>',
        default: '<div class="default-slot">extra</div>',
      },
    })

    expect(wrapper.find('.mobile-header-slot').exists()).toBe(true)
    expect(wrapper.find('.media-slot').exists()).toBe(true)
    expect(wrapper.find('.info-slot').exists()).toBe(true)
    expect(wrapper.find('.default-slot').exists()).toBe(true)
    expect(wrapper.find('.custom-info-content').exists()).toBe(true)
    expect(wrapper.find('.custom-desktop-close').exists()).toBe(true)

    const closeButtons = wrapper.findAll('button')
    expect(closeButtons).toHaveLength(2)

    await closeButtons[0].trigger('click')
    await closeButtons[1].trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(2)
  })
})
