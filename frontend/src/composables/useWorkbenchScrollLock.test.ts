// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useWorkbenchScrollLock } from '@/composables/useWorkbenchScrollLock'

describe('useWorkbenchScrollLock', () => {
  it('locks the container overflow and restores overflow plus scroll position when closed', async () => {
    const element = document.createElement('div')
    element.style.overflow = 'auto'
    element.scrollTop = 120
    const active = ref(false)

    const Host = defineComponent({
      setup() {
        const contentRef = ref<HTMLElement | null>(element)

        useWorkbenchScrollLock(contentRef, active)
        return {}
      },
      template: '<div />'
    })

    mount(Host)

    expect(element.style.overflow).toBe('auto')
    expect(element.scrollTop).toBe(120)

    active.value = true
    await nextTick()

    expect(element.style.overflow).toBe('hidden')

    element.scrollTop = 16
    active.value = false
    await nextTick()

    expect(element.style.overflow).toBe('auto')
    expect(element.scrollTop).toBe(120)
  })

  it('releases the lock on unmount even if the workbench is still active', () => {
    const element = document.createElement('div')
    element.style.overflow = 'scroll'
    element.scrollTop = 88

    const Host = defineComponent({
      setup() {
        const contentRef = ref<HTMLElement | null>(element)
        const active = ref(true)

        useWorkbenchScrollLock(contentRef, active)

        return {}
      },
      template: '<div />'
    })

    const wrapper = mount(Host)

    expect(element.style.overflow).toBe('hidden')

    wrapper.unmount()

    expect(element.style.overflow).toBe('scroll')
    expect(element.scrollTop).toBe(88)
  })
})
