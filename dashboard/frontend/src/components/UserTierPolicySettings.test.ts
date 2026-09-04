// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchUserTierPolicyConfig: vi.fn(),
  updateUserTierPolicyConfig: vi.fn(),
}))
const messageMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('../api/api', () => apiMocks)
vi.mock('ant-design-vue/es/message', () => ({ default: messageMocks }))

import UserTierPolicySettings from './UserTierPolicySettings.vue'

const buildRank = (flashbackBonus: number) => ({
  upgrade: { invitations: 0, checkins: 0, generations: 0, channel_member: false },
  benefits: {
    checkin_enabled: true,
    checkin_credits: 10,
    web_access: true,
    flashback_bonus: flashbackBonus,
    queue_pressure_exempt: false,
  },
  video: { resolutions: ['512p'], durations: ['5s'] },
  priority_rules: [],
})

const buildIdentity = (flashbackBonus: number) => ({
  benefits: {
    mortal_checkin_access: false,
    checkin_bonus: 0,
    web_access: false,
    concurrent_tasks: 3,
    favorite_limit: 100,
    flashback_bonus: flashbackBonus,
    queue_pressure_exempt: false,
  },
  video: { resolutions: ['512p'], durations: ['5s'] },
  priority_rules: [],
})

const buildResponse = () => ({
  key: 'user_tier_policy_config:v1',
  updated_at: null,
  config: {
    schema_version: 2,
    capacity_combination_rule: 'additive',
    flashback_base: 5,
    cultivation_ranks: {
      凡人: buildRank(0),
      练气期: buildRank(2),
      筑基期: buildRank(3),
      金丹期: buildRank(4),
      元婴期: buildRank(5),
    },
    membership_identities: {
      外门弟子: buildIdentity(2),
      内门弟子: buildIdentity(4),
      核心弟子: buildIdentity(7),
      真传弟子: buildIdentity(10),
    },
    low_trust: {
      enabled: true,
      checkin_threshold: 7,
      successful_order_exempt: true,
      referral_count_threshold: 100,
      successful_invitee_rate_percent_threshold: 3,
      trusted_priority_bonus: 40,
      new_user_generation_threshold: 2,
      new_user_base_priority: 30,
    },
  },
})

describe('UserTierPolicySettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchUserTierPolicyConfig.mockResolvedValue(buildResponse())
    apiMocks.updateUserTierPolicyConfig.mockImplementation(async payload => ({
      ...buildResponse(),
      config: payload,
    }))
  })

  it('loads the three policy scopes and saves the current full snapshot', async () => {
    const wrapper = mount(UserTierPolicySettings)
    await flushPromises()

    expect(wrapper.text()).toContain('等级权益配置')
    expect(wrapper.text()).toContain('晋升条件')
    expect(wrapper.text()).toContain('身份到期会自动回落')
    expect(wrapper.text()).toContain('低信任免费层判定')
    expect(wrapper.text()).toContain('基础容量')
    expect(wrapper.text()).toContain('叠加计算')
    expect(wrapper.text()).toContain('7–20')

    const vm = wrapper.vm as any
    vm.config.cultivation_ranks['元婴期'].benefits.flashback_bonus = 6
    await wrapper.vm.$nextTick()
    await vm.savePolicy()

    expect(apiMocks.updateUserTierPolicyConfig).toHaveBeenCalledOnce()
    expect(apiMocks.updateUserTierPolicyConfig.mock.calls[0][0].cultivation_ranks['元婴期'].benefits.flashback_bonus).toBe(6)
    expect(messageMocks.success).toHaveBeenCalledWith('等级权益已保存并生效')
  })
})
