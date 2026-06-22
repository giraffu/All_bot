// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api/api', () => ({
  fetchRunPodOperations: vi.fn().mockResolvedValue({ operations: [] }),
  fetchRunPodProfiles: vi.fn().mockRejectedValue(new Error('profiles unavailable')),
  scaleRunPodCapacity: vi.fn(),
  terminateRunPodOperation: vi.fn(),
}))

import RunPodCapacityManager from './RunPodCapacityManager.vue'

const ButtonStub = defineComponent({
  name: 'ButtonStub',
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
})

const ModalStub = defineComponent({
  name: 'ModalStub',
  props: ['open'],
  template: '<div v-if="open"><slot /></div>',
})

const SelectStub = defineComponent({
  name: 'SelectStub',
  props: ['options', 'value'],
  emits: ['update:value'],
  template: `
    <select :value="value" @change="$emit('update:value', $event.target.value)">
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  `,
})

const slotStub = name => defineComponent({
  name,
  props: ['color'],
  template: '<div><slot name="icon" /><slot /></div>',
})

const mountRunPodCapacityManager = () =>
  mount(RunPodCapacityManager, {
    global: {
      stubs: {
        'a-button': ButtonStub,
        'a-modal': ModalStub,
        'a-select': SelectStub,
        'a-input-number': defineComponent({
          name: 'InputNumberStub',
          props: ['value'],
          emits: ['update:value'],
          template: '<input type="number" :value="value" />',
        }),
        'a-tag': slotStub('TagStub'),
        'a-popconfirm': slotStub('PopconfirmStub'),
        CloudServerOutlined: slotStub('CloudServerOutlinedStub'),
        DeleteOutlined: slotStub('DeleteOutlinedStub'),
        PlusOutlined: slotStub('PlusOutlinedStub'),
        StopOutlined: slotStub('StopOutlinedStub'),
      },
    },
  })

describe('RunPodCapacityManager', () => {
  it('keeps video profiles available in the fallback profile list', async () => {
    const wrapper = mountRunPodCapacityManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('scail2 / 视频生视频')
    expect(wrapper.text()).toContain('ltx_video / 高级图生视频')
  })
})
