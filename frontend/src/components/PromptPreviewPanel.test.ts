// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PromptPreviewPanel from '@/components/PromptPreviewPanel.vue'

describe('PromptPreviewPanel', () => {
  it('renders prompt text and emits copy when copy button is enabled', async () => {
    const wrapper = mount(PromptPreviewPanel, {
      props: {
        title: '提示词预览',
        prompt: 'first line\nsecond line\nthird line\nfourth line\nfifth line',
        expandLabel: '展开全文',
        collapseLabel: '收起',
        showCopy: true,
        copyLabel: '复制提示词',
        collapsedLines: 2,
      },
    })

    expect(wrapper.text()).toContain('提示词预览')
    expect(wrapper.text()).toContain('复制提示词')
    expect(wrapper.find('.prompt-preview-content').classes()).toContain('is-collapsed')

    await wrapper.get('.prompt-preview-action-btn').trigger('click')
    expect(wrapper.emitted('copy')).toHaveLength(1)

    await wrapper.get('.prompt-preview-toggle').trigger('click')
    expect(wrapper.find('.prompt-preview-content').classes()).not.toContain('is-collapsed')
    expect(wrapper.text()).toContain('收起')
  })

  it('does not render when prompt is empty', () => {
    const wrapper = mount(PromptPreviewPanel, {
      props: {
        title: '提示词预览',
        prompt: '   ',
        expandLabel: '展开全文',
        collapseLabel: '收起',
      },
    })

    expect(wrapper.html()).toBe('<!--v-if-->')
  })

  it('masks the trailing half of prompt text when enabled', () => {
    const wrapper = mount(PromptPreviewPanel, {
      props: {
        title: '提示词预览',
        prompt: 'abcdefghij',
        expandLabel: '展开全文',
        collapseLabel: '收起',
        maskText: true,
        visibleRatio: 0.5,
      },
    })

    const contentText = wrapper.get('.prompt-preview-content').text()
    expect(contentText.startsWith('abcde')).toBe(true)
    expect(contentText).not.toContain('fghij')
    expect(/[•·◦*]/.test(contentText)).toBe(true)
  })
})
