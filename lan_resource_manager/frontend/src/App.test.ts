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
        {
          slot_id: 'blocked',
          profile: 'wan22',
          phase: 'blocked_oom_32gb',
          enabled: false,
          retargetable: false,
          switchable: false,
          task_types: [],
        },
      ],
      blocked_observations: [],
    },
  ],
  state: { status: 'passed', drift: [], captured_at: new Date().toISOString(), stale: false },
  active_operation: null,
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('security/csrf')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ csrf_token: 'x' }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(fleet) })
    }),
  )
  vi.stubGlobal('EventSource', class {})
})
afterEach(() => vi.unstubAllGlobals())

describe('LAN AIO cards', () => {
  it('shows current and blocked profiles and opens typed confirmation only for stable target', async () => {
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('i2i_pro')
    expect(wrapper.text()).toContain('wan22')
    const buttons = wrapper.findAll('button.candidate')
    expect(buttons[2].attributes('disabled')).toBeDefined()
    await buttons[1].trigger('click')
    expect(wrapper.text()).toContain('确认单卡类型切换')
    expect(wrapper.find('.danger-button').attributes('disabled')).toBeDefined()
  })

  it('blocks every switch when live state is stale', async () => {
    fleet.state.stale = true
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('状态已过期')
    expect(wrapper.findAll('button.candidate').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    fleet.state.stale = false
  })
})

describe('deployment workspace', () => {
  it('switches tabs, filters prod-only modules, and requires a plan confirmation', async () => {
    const catalog = {
      modules: {
        'central-api': { artifacts: ['central-api'] },
        dashboard: { artifacts: ['dashboard-backend', 'dashboard-frontend'] },
      },
      environments: {
        test: {
          label: '测试环境',
          modules: ['central-api'],
          maintenance_supported: true,
        },
        prod: {
          label: '正式环境',
          modules: ['central-api', 'dashboard'],
          maintenance_supported: true,
        },
      },
    }
    const candidate = {
      main_sha: 'a'.repeat(40),
      deployable_sha: 'a'.repeat(40),
      scope: 'runtime',
      ci: { status: 'completed', conclusion: 'success', run_id: 41 },
      bundle: { status: 'ready' },
      build: null,
      blockers: [],
    }
    const environment = {
      environment: 'test',
      current_sha: 'b'.repeat(40),
      maintenance: { enabled: false, owner: null, can_disable: false },
      active_transaction: null,
      config_drift: false,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const body = url.includes('security/csrf')
          ? { csrf_token: 'x' }
          : url.includes('deployments/catalog')
            ? catalog
            : url.includes('releases/candidate')
              ? candidate
              : url.includes('environments/test/status')
                ? environment
                : fleet
        return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
      }),
    )
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-tab="deploy"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('模块构建部署')
    expect(wrapper.text()).toContain('central-api')
    expect(wrapper.text()).not.toContain('dashboard-backend')
    expect(wrapper.text()).toContain('可信 bundle 已就绪')
    expect(wrapper.get('[data-action="create-plan"]').attributes('disabled')).toBeUndefined()
  })
})
