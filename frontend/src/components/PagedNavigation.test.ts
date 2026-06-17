// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PagedNavigation from '@/components/PagedNavigation.vue'

describe('PagedNavigation', () => {
  it('emits a page change from the jump input', async () => {
    const wrapper = mount(PagedNavigation, {
      props: {
        currentPage: 1,
        totalPages: 1533,
        showJump: true,
        compact: true,
      },
    })

    await wrapper.get('input[aria-label="跳转页码，1 到 1533"]').setValue('88')
    await wrapper.get('form.pagination-jump').trigger('submit')

    expect(wrapper.emitted('change')).toEqual([[88]])
  })

  it('keeps jump input numeric and clamps oversized page numbers', async () => {
    const wrapper = mount(PagedNavigation, {
      props: {
        currentPage: 1,
        totalPages: 9,
        showJump: true,
      },
    })

    const input = wrapper.get('input[aria-label="跳转页码，1 到 9"]')
    await input.setValue('12x3')

    expect((input.element as HTMLInputElement).value).toBe('12')

    await wrapper.get('form.pagination-jump').trigger('submit')

    expect(wrapper.emitted('change')).toEqual([[9]])
  })

  it('renders minimal page controls without jump input', async () => {
    const wrapper = mount(PagedNavigation, {
      props: {
        currentPage: 3,
        totalPages: 9,
        showJump: true,
        compact: true,
        minimal: true,
      },
    })

    expect(wrapper.text()).toContain('3 / 9')
    expect(wrapper.find('form.pagination-jump').exists()).toBe(false)

    await wrapper.get('button[aria-label="上一页"]').trigger('click')
    await wrapper.get('button[aria-label="下一页"]').trigger('click')

    expect(wrapper.emitted('change')).toEqual([[2], [4]])
  })
})
