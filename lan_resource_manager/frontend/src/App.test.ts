import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'

const fleet = {
  physical_slots: [
    {
      physical_slot: 'gpu-002:gpu1',
      node_id: 'gpu-002',
      gpu_index: 1,
      host_port: 8191,
      current: { slot_id: 'current', profile: 'i2i_pro', state: 'running' },
      worker: { status: 'idle', current_task_type: null },
      candidates: [
        {
          slot_id: 'current',
          profile: 'i2i_pro',
          phase: 'catalog_ready',
          enabled: true,
          retargetable: true,
          switchable: false,
          task_types: [],
          cache: { cache_state: 'ready' },
        },
        {
          slot_id: 'target',
          profile: 'image_to_video',
          phase: 'catalog_ready',
          enabled: true,
          retargetable: true,
          switchable: true,
          task_types: [],
          cache: { cache_state: 'ready' },
        },
      ],
      blocked_observations: [],
    },
  ],
  state: {
    status: 'passed',
    drift: [],
    captured_at: new Date().toISOString(),
    stale: false,
  },
  active_operation: null,
}

const scan = {
  main_sha: 'a'.repeat(40),
  slots: Array.from({ length: 8 }, (_, index) => ({
    slot: String.fromCharCode(65 + index),
    branch: null,
    head: 'a'.repeat(40),
    clean: true,
    at_base: true,
  })),
  queue: {
    pending: [
      {
        id: 'one',
        slot: 'A',
        status: 'pending',
        branch: 'codex/a-task',
        head: 'c'.repeat(40),
      },
    ],
    integrating: [],
    'needs-rebase': [
      { id: 'old', slot: 'C', status: 'needs-rebase', head: 'd'.repeat(40) },
    ],
    completed: [],
  },
}

const catalog = {
  modules: {
    'central-api': {
      kind: 'image',
      adapter: 'compose-image',
      environments: ['test', 'prod'],
      build_only: false,
      requires_target: false,
    },
    'web-api': {
      kind: 'image',
      adapter: 'compose-image',
      environments: ['test', 'prod'],
      build_only: false,
      requires_target: false,
    },
    'worker-agent': {
      kind: 'image',
      adapter: 'compose-image',
      environments: ['test'],
      build_only: false,
      requires_target: false,
    },
    'payment-api': {
      kind: 'image',
      adapter: 'compose-image',
      environments: ['prod'],
      build_only: false,
      requires_target: false,
    },
  },
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const body = url.includes('security/csrf')
        ? { csrf_token: 'x' }
        : url.includes('workspaces/scan')
          ? scan
          : url.includes('deployments/catalog')
            ? catalog
            : fleet
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    }),
  )
  vi.stubGlobal('EventSource', class {})
})
afterEach(() => vi.unstubAllGlobals())

describe('LAN AIO cards', () => {
  it('keeps typed confirmation for a stable single-slot switch', async () => {
    const wrapper = mount(App)
    await flushPromises()
    const buttons = wrapper.findAll('button.candidate')
    expect(buttons[0].attributes('disabled')).toBeDefined()
    await buttons[1].trigger('click')
    expect(wrapper.text()).toContain('确认单卡类型切换')
    expect(wrapper.find('.danger-button').attributes('disabled')).toBeDefined()
  })
})

describe('module release control', () => {
  it('scans all slots and exposes selected integration and alignment', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-tab="deploy"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.workspace-option')).toHaveLength(8)
    expect(wrapper.text()).toContain('pending handoff')
    expect(wrapper.text()).toContain('needs-rebase')
    expect(wrapper.find('[data-action="integrate-selected"]').exists()).toBe(true)
    expect(wrapper.find('[data-action="align-selected"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('可信 bundle')
    expect(wrapper.text()).not.toContain('生成受控发布计划')
  })

  it('limits test selection to two modules and exposes prod modules', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-tab="deploy"]').trigger('click')
    await flushPromises()
    const testModules = wrapper.findAll('.module-option')
    expect(testModules).toHaveLength(3)
    await testModules[0].trigger('click')
    await testModules[1].trigger('click')
    await testModules[2].trigger('click')
    expect(wrapper.text()).toContain('测试环境每次最多选择两个模块')
    expect(wrapper.find('[data-action="build-selected"]').exists()).toBe(true)
    expect(wrapper.find('[data-action="deploy-selected"]').exists()).toBe(true)

    await wrapper.findAll('.environment-switch button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('payment-api')
    expect(wrapper.text()).toContain('正式环境可在管理后台多选模块')
  })
})
