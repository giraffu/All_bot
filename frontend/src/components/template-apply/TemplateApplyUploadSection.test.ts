// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TemplateApplyUploadSection from '@/components/template-apply/TemplateApplyUploadSection.vue'

const UploadStub = defineComponent({
  name: 'AUpload',
  props: ['beforeUpload'],
  template: '<div class="upload-control"><slot /></div>',
})

describe('TemplateApplyUploadSection', () => {
  it('shows an explicit replacement control for a prefilled template image', () => {
    const beforeUpload = vi.fn()
    const wrapper = mount(TemplateApplyUploadSection, {
      props: {
        filePreview: 'https://example.com/reference.png',
        uploadingSlots: {},
        progressBySlot: {},
        beforeUpload,
        replaceText: '替换这张参考图',
        showRemove: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          AUpload: UploadStub,
          AUploadDragger: true,
          AProgress: true,
          CloseCircleOutlined: true,
          InboxOutlined: true,
        },
      },
    })

    expect(wrapper.text()).toContain('替换这张参考图')
    expect(wrapper.find('.upload-control').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="remove"]').exists()).toBe(false)
  })
})
