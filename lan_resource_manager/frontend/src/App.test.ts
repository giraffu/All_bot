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
