// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'

describe('TaskResultPreviewPanel', () => {
  it('renders pending queue copy without misleading 0 percent and keeps queuePos=0 visible', () => {
    const wrapper = mount(TaskResultPreviewPanel, {
      props: {
        currentTask: {
          status: 'pending',
          progress: 0,
          queuePos: 0,
          cancelRequested: false,
        },
      },
      global: {
        stubs: {
          'a-spin': { template: '<div class="spin-stub"></div>' },
          'a-progress': { template: '<div class="progress-stub"></div>' },
          'a-button': { template: '<button><slot /></button>' },
          'a-image': { template: '<img />' },
        },
      },
    })

    expect(wrapper.text()).toContain('正在排队中...')
    expect(wrapper.text()).toContain('前面还有 0 人排队')
    expect(wrapper.text()).not.toContain('正在生成中... 0%')
    expect(wrapper.find('.progress-stub').exists()).toBe(false)
  })

  it('renders running progress once execution has started', () => {
    const wrapper = mount(TaskResultPreviewPanel, {
      props: {
        currentTask: {
          status: 'running',
          progress: 37,
          cancelRequested: false,
        },
      },
      global: {
        stubs: {
          'a-spin': { template: '<div class="spin-stub"></div>' },
          'a-progress': { template: '<div class="progress-stub"></div>' },
          'a-button': { template: '<button><slot /></button>' },
          'a-image': { template: '<img />' },
        },
      },
    })

    expect(wrapper.text()).toContain('正在生成中... 37%')
    expect(wrapper.find('.progress-stub').exists()).toBe(true)
  })
})
