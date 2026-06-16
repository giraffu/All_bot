// @vitest-environment jsdom

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const queueStatsMocks = vi.hoisted(() => ({
  statusRef: null,
  workersRef: null,
  concurrencyStatsRef: null,
}))

vi.mock('../composables/useQueueStatsMonitor', async () => {
  const { computed, ref } = await vi.importActual('vue')
  queueStatsMocks.statusRef ??= ref({})
  queueStatsMocks.workersRef ??= ref([])
  queueStatsMocks.concurrencyStatsRef ??= ref([])

  return {
    useQueueStatsMonitor: () => ({
      status: queueStatsMocks.statusRef,
      workers: queueStatsMocks.workersRef,
      concurrencyStats: queueStatsMocks.concurrencyStatsRef,
      cleaning: ref(false),
      syncing: ref({}),
      queueByTypeDisplay: computed(() => []),
      cleanZombies: vi.fn(),
      syncLock: vi.fn(),
      updateQueue: vi.fn(),
    }),
  }
})

const slotStub = (name) => defineComponent({
  name,
  template: '<div><slot name="title" /><slot name="icon" /><slot name="prefix" /><slot name="suffix" /><slot /></div>',
})

const BadgeStub = defineComponent({
  name: 'BadgeStub',
  props: ['text'],
  template: '<span class="badge-stub">{{ text }}</span>',
})

const StatisticStub = defineComponent({
  name: 'StatisticStub',
  props: ['title', 'value'],
  template: '<div><span>{{ title }}</span><span>{{ value }}</span><slot name="prefix" /><slot name="suffix" /></div>',
})

const TableColumnStub = defineComponent({
  name: 'TableColumnStub',
  template: '<div />',
})

const mountQueueStats = async () => {
  const QueueStats = (await import('./QueueStats.vue')).default
  return mount(QueueStats, {
    global: {
      stubs: {
        'a-button': slotStub('AButtonStub'),
        'a-card': slotStub('ACardStub'),
        'a-col': slotStub('AColStub'),
        'a-row': slotStub('ARowStub'),
        'a-tag': slotStub('ATagStub'),
        'a-table': slotStub('ATableStub'),
        'a-table-column': TableColumnStub,
        'a-badge': BadgeStub,
        'a-statistic': StatisticStub,
        'a-progress': slotStub('AProgressStub'),
        'a-empty': slotStub('AEmptyStub'),
        RunPodCapacityManager: slotStub('RunPodCapacityManagerStub'),
        RunPodWorkerActions: slotStub('RunPodWorkerActionsStub'),
      },
    },
  })
}

describe('QueueStats worker health display', () => {
  beforeEach(() => {
    queueStatsMocks.statusRef = ref({
      queue_size: 0,
      queue_by_type: {},
      active_workers: 0,
      healthy_workers: 0,
      error_workers: 0,
      quarantined_workers: 0,
      workers_by_status: {},
      comfy_online: false,
      concurrency_locks: 0,
    })
    queueStatsMocks.workersRef = ref([])
    queueStatsMocks.concurrencyStatsRef = ref([])
    vi.resetModules()
  })

  it('shows all-fault status and does not render unhealthy workers as idle', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      active_workers: 2,
      healthy_workers: 0,
      error_workers: 1,
      quarantined_workers: 1,
      comfy_online: false,
    }
    queueStatsMocks.workersRef.value = [
      {
        agent_id: 'agent-error',
        types: 'ltx_video',
        status: 'error',
        last_seen: Date.now() / 1000,
        health_reason: 'comfy_probe_failed',
        last_error: 'ComfyUI /system_stats probe failed',
        last_error_at: Date.now() / 1000 - 10,
        consecutive_failures: 3,
      },
      {
        agent_id: 'agent-quarantine',
        types: 'wan22_video_v2',
        status: 'quarantined',
        last_seen: Date.now() / 1000,
        health_reason: 'task_infra_failures',
        last_error: 'ComfyUI upload timeout',
        quarantined_until: Date.now() / 1000 + 120,
        consecutive_failures: 3,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('ComfyUI 全部故障')
    expect(wrapper.text()).toContain('故障')
    expect(wrapper.text()).toContain('已隔离')
    expect(wrapper.text()).toContain('ComfyUI /system_stats probe failed')
    expect(wrapper.text()).toContain('ComfyUI upload timeout')
    expect(wrapper.text()).not.toContain('等待任务分发中...')
  })

  it('shows partial fault status when at least one worker remains healthy', async () => {
    queueStatsMocks.statusRef.value = {
      ...queueStatsMocks.statusRef.value,
      active_workers: 3,
      healthy_workers: 2,
      error_workers: 1,
      quarantined_workers: 0,
      comfy_online: true,
    }
    queueStatsMocks.workersRef.value = [
      { agent_id: 'agent-idle', types: 'img2img', status: 'idle', last_seen: Date.now() / 1000 },
      { agent_id: 'agent-running', types: 'ltx_video', status: 'running', last_seen: Date.now() / 1000 },
      {
        agent_id: 'agent-error',
        types: 'wan22_video_v2',
        status: 'error',
        last_seen: Date.now() / 1000,
        last_error: 'ComfyUI node crashed',
        consecutive_failures: 3,
      },
    ]

    const wrapper = await mountQueueStats()

    expect(wrapper.text()).toContain('ComfyUI 部分故障')
    expect(wrapper.text()).toContain('空闲')
    expect(wrapper.text()).toContain('忙碌')
    expect(wrapper.text()).toContain('故障')
  })
})
