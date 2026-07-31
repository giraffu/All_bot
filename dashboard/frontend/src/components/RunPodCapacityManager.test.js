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
      min_runpod_lifetime_seconds: 1800,
      runpod_fault_restart_seconds: 300,
      runpod_bootstrap_timeout_seconds: 2400,
      runpod_bootstrap_replacement_limit: 2,
      runpod_bootstrap_replacement_window_seconds: 7200,
      max_runpods_per_profile: 5,
    },
    decisions: [
      {
        profile: 'img2img',
        action: 'scale_up',
        reason: 'scale_up: estimated non-low-trust clear time 1900s exceeds 1800s',
        estimated_clear_time_seconds: 1900,
        capacity_status: 'ok',
      },
      {
        profile: 'i2i_pro',
        action: 'hold',
        reason: 'hold: estimated non-low-trust clear time within threshold',
      },
      {
        profile: 'scail2',
        action: 'restart',
        reason: 'restart: runpod fault persisted 350s',
      },
      {
        profile: 'image_to_video',
        action: 'enable',
        reason: 'enable: runpod paused worker available',
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
  scaleRunPodCapacity,
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
  emits: ['ok'],
  template: '<div v-if="open"><slot /><button class="modal-ok" @click="$emit(\'ok\')">submit</button></div>',
})

const PaginationStub = defineComponent({
  name: 'PaginationStub',
  props: ['current', 'pageSize', 'total'],
  emits: ['update:current'],
  template: '<button class="page-2" @click="$emit(\'update:current\', 2)">page 2 / {{ total }}</button>',
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
        'a-pagination': PaginationStub,
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
    vi.mocked(scaleRunPodCapacity).mockResolvedValue({
      batch_id: 'batch-1',
      operations: [
        { id: 'op-1', action: 'add', profile: 'img2img', slot: '01', status: 'pending' },
        { id: 'op-2', action: 'add', profile: 'img2img', slot: '02', status: 'pending' },
      ],
    })
    vi.mocked(fetchRunPodAutoscaler).mockResolvedValue({
      enabled: true,
      configured_enabled: true,
      control_enabled: true,
      config: {
        scale_up_wait_seconds: 1800,
        scale_down_wait_seconds: 60,
        cooldown_seconds: 600,
        min_runpod_lifetime_seconds: 1800,
        runpod_fault_restart_seconds: 300,
        runpod_bootstrap_timeout_seconds: 2400,
        runpod_bootstrap_replacement_limit: 2,
        runpod_bootstrap_replacement_window_seconds: 7200,
        max_runpods_per_profile: 5,
      },
      decisions: [
        {
          profile: 'img2img',
          action: 'scale_up',
          reason: 'scale_up: estimated non-low-trust clear time 1900s exceeds 1800s',
          estimated_clear_time_seconds: 1900,
          capacity_status: 'ok',
        },
        {
          profile: 'i2i_pro',
          action: 'hold',
          reason: 'hold: estimated non-low-trust clear time within threshold',
        },
        {
          profile: 'scail2',
          action: 'restart',
          reason: 'restart: runpod fault persisted 350s',
        },
        {
          profile: 'image_to_video',
          action: 'enable',
          reason: 'enable: runpod paused worker available',
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
    expect(wrapper.text()).toContain('ltx_t2v / Sulphur + Ingredients')
    expect(wrapper.text()).toContain('pornmaster_flux2 / 自由P图 v2')
    expect(wrapper.text()).toContain('pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池')
  })

  it('renders autoscaler status and decisions', async () => {
    vi.mocked(fetchRunPodOperations).mockResolvedValue({
      operations: [
        {
          id: 'auto-op',
          action: 'add',
          profile: 'img2img',
          source: 'autoscaler',
          trigger_reason: 'scale_up: estimated non-low-trust clear time 1900s exceeds 1800s',
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
    expect(wrapper.text()).toContain('清空阈值 1800s')
    expect(wrapper.text()).toContain('最短生命周期 1800s')
    expect(wrapper.text()).toContain('故障重启 300s')
    expect(wrapper.text()).toContain('启动超时 2400s')
    expect(wrapper.text()).toContain('替换上限 2')
    expect(wrapper.text()).toContain('扩容')
    expect(wrapper.text()).toContain('重启')
    expect(wrapper.text()).toContain('开启')
    expect(wrapper.text()).toContain('scale_up: estimated non-low-trust clear time 1900s exceeds 1800s')
    expect(wrapper.text()).toContain('restart: runpod fault persisted 350s')
    expect(wrapper.text()).toContain('enable: runpod paused worker available')
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

  it('keeps the modal open after submitting and displays operation pages with slots', async () => {
    vi.mocked(fetchRunPodOperations).mockResolvedValue({
      operations: Array.from({ length: 8 }, (_value, index) => ({
        id: `op-${index + 1}`,
        action: 'add',
        profile: 'img2img',
        slot: String(index + 1).padStart(2, '0'),
        status: 'running',
        requested_count: 1,
      })),
    })
    const wrapper = mountRunPodCapacityManager()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('slot 01')
    expect(wrapper.text()).not.toContain('slot 07')
    await wrapper.get('.page-2').trigger('click')
    expect(wrapper.text()).toContain('slot 07')

    await wrapper.get('.modal-ok').trigger('click')
    await flushPromises()

    expect(scaleRunPodCapacity).toHaveBeenCalled()
    expect(wrapper.find('.modal-ok').exists()).toBe(true)
    expect(wrapper.text()).toContain('slot 01')
  })
})
