// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import LabReferenceTray from '@/components/lab/LabReferenceTray.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => ({
      'lab.workbench.reference_count': '1 张参考图',
      'lab.workbench.remove_reference': '删除参考图',
    }[key] ?? key),
  }),
}))

vi.mock('@ant-design/icons-vue', async () => {
  const { defineComponent } = await vi.importActual<typeof import('vue')>('vue')
  const stub = (name: string) => defineComponent({
    name,
    template: `<span class="${name}" />`,
  })

  return {
    CloseOutlined: stub('close-icon'),
    LockOutlined: stub('lock-icon'),
  }
})

const ImageStub = defineComponent({
  name: 'AImage',
  props: ['src'],
  template: '<img class="a-image-stub" :src="src" alt="">',
})

const ProgressStub = defineComponent({
  name: 'AProgress',
  props: ['percent'],
  template: '<div class="a-progress-stub">{{ percent }}</div>',
})

const mountTray = (items: InstanceType<typeof LabReferenceTray>['$props']['items']) => mount(LabReferenceTray, {
  props: {
    title: '自由P图',
    items,
  },
  global: {
    stubs: {
      'a-image': ImageStub,
      'a-progress': ProgressStub,
    },
  },
})

describe('LabReferenceTray', () => {
  it('renders an accessible top-right remove button and emits the item index', async () => {
    const wrapper = mountTray([
      {
        key: 'uploads/reference.png',
        preview: 'blob:reference',
        name: 'reference.png',
      },
    ])

    const removeButton = wrapper.get('.lab-reference-tray__remove')
    expect(removeButton.attributes('aria-label')).toBe('删除参考图')
    expect(removeButton.element.tagName).toBe('BUTTON')
    expect(removeButton.classes()).toEqual(expect.arrayContaining(['right-0.5', 'top-0.5']))

    await removeButton.trigger('click')

    expect(wrapper.emitted('remove')).toEqual([[0]])
  })

  it('does not show the remove button for locked or uploading references', () => {
    const wrapper = mountTray([
      {
        key: 'locked-reference',
        preview: '/locked.png',
        name: 'locked.png',
        locked: true,
      },
      {
        key: 'pending-reference',
        preview: 'blob:pending',
        name: 'pending.png',
        uploading: true,
      },
    ])

    expect(wrapper.find('.lab-reference-tray__remove').exists()).toBe(false)
  })
})
