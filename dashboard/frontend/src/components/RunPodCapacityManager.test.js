// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/api', () => ({
  controlRunPodAutoscaler: vi.fn().mockResolvedValue({
    enabled: false,
    configured_enabled: true,
    control_enabled: false,
    config: {},
    decisions: [],
  }),
  fetchRunPodAutoscaler: vi.fn().mockResolvedValue({
    enabled: true,
    configured_enabled: true,
    control_enabled: true,
    config: {
      scale_up_wait_seconds: 1800,
      scale_down_wait_seconds: 60,
      cooldown_seconds: 600,
      max_runpods_per_profile: 5,
    },
    decisions: [
      {
        profile: 'img2img',
        action: 'scale_up',
        reason: 'pending wait 1900s exceeds 1800s',
      },
      {
        profile: 'i2i_pro',
        action: 'hold',
        reason: 'within thresholds',
      },
    ],
  }),
  fetchRunPodOperations: vi.fn().mockResolvedValue({ operations: [] }),
  fetchRunPodProfiles: vi.fn().mockRejectedValue(new Error('profiles unavailable')),
  scaleRunPodCapacity: vi.fn(),
  terminateRunPodOperation: vi.fn(),
}))

import {
  controlRunPodAutoscaler,
  fetchRunPodAutoscaler,
  fetchRunPodOperations,
} from '../api/api'
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
        PauseCircleOutlined: slotStub('PauseCircleOutlinedStub'),
        PlayCircleOutlined: slotStub('PlayCircleOutlinedStub'),
        PlusOutlined: slotStub('PlusOutlinedStub'),
        RobotOutlined: slotStub('RobotOutlinedStub'),
        StopOutlined: slotStub('StopOutlinedStub'),
      },
    },
  })

describe('RunPodCapacityManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchRunPodOperations).mockResolvedValue({ operations: [] })
    vi.mocked(fetchRunPodAutoscaler).mockResolvedValue({
      enabled: true,
      configured_enabled: true,
      control_enabled: true,
      config: {
        scale_up_wait_seconds: 1800,
        scale_down_wait_seconds: 60,
        cooldown_seconds: 600,
        max_runpods_per_profile: 5,
      },
      decisions: [
        {
          profile: 'img2img',
          action: 'scale_up',
          reason: 'pending wait 1900s exceeds 1800s',
        },
        {
          profile: 'i2i_pro',
          action: 'hold',
          reason: 'within thresholds',
        },
      ],
    })
    vi.mocked(controlRunPodAutoscaler).mockResolvedValue({
      enabled: false,
      configured_enabled: true,
      control_enabled: false,
      config: {},
      decisions: [],
    })
  })

  it('keeps video profiles available in the fallback profile list', async () => {
    const wrapper = mountRunPodCapacityManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('scail2 / 视频生视频')
    expect(wrapper.text()).toContain('ltx_video / 高级图生视频')
  })

  it('renders autoscaler status and decisions', async () => {
    vi.mocked(fetchRunPodOperations).mockResolvedValue({
      operations: [
        {
          id: 'auto-op',
          action: 'add',
          profile: 'img2img',
          source: 'autoscaler',
          trigger_reason: 'pending wait 1900s exceeds 1800s',
          status: 'running',
          requested_count: 1,
        },
      ],
    })
    const wrapper = mountRunPodCapacityManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('自动管理')
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('扩容等待 1800s')
    expect(wrapper.text()).toContain('扩容')
    expect(wrapper.text()).toContain('pending wait 1900s exceeds 1800s')
    expect(wrapper.text()).toContain('自动')
  })

  it('can pause autoscaler from the manager modal', async () => {
    const wrapper = mountRunPodCapacityManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const pauseButton = wrapper
      .findAll('button')
      .find(button => button.text().includes('暂停自动管理'))
    expect(pauseButton).toBeTruthy()
    await pauseButton?.trigger('click')
    await flushPromises()

    expect(controlRunPodAutoscaler).toHaveBeenCalledWith({
      enabled: false,
      reason: 'dashboard pause',
    })
  })
})
