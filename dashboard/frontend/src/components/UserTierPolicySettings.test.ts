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

const buildRank = (flashback: number) => ({
  upgrade: { invitations: 0, checkins: 0, generations: 0, channel_member: false },
  benefits: {
    checkin_enabled: true,
    checkin_credits: 10,
    web_access: true,
    flashback_bottles: flashback,
    queue_pressure_exempt: false,
  },
  video: { resolutions: ['512p'], durations: ['5s'] },
  priority_rules: [],
})

const buildIdentity = (flashback: number) => ({
  benefits: {
    mortal_checkin_access: false,
    checkin_bonus: 0,
    web_access: false,
    concurrent_tasks: 3,
    favorite_limit: 100,
    flashback_bottles: flashback,
    queue_pressure_exempt: false,
  },
  video: { resolutions: ['512p'], durations: ['5s'] },
  priority_rules: [],
})

const buildResponse = () => ({
  key: 'user_tier_policy_config:v1',
  updated_at: null,
  config: {
    schema_version: 1,
    capacity_combination_rule: 'max',
    cultivation_ranks: {
      凡人: buildRank(8),
      练气期: buildRank(9),
      筑基期: buildRank(10),
      金丹期: buildRank(12),
      元婴期: buildRank(14),
    },
    membership_identities: {
      外门弟子: buildIdentity(8),
      内门弟子: buildIdentity(10),
      核心弟子: buildIdentity(12),
      真传弟子: buildIdentity(14),
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

    const vm = wrapper.vm as any
    vm.config.cultivation_ranks['筑基期'].benefits.flashback_bottles = 11
    await wrapper.vm.$nextTick()
    await vm.savePolicy()

    expect(apiMocks.updateUserTierPolicyConfig).toHaveBeenCalledOnce()
    expect(apiMocks.updateUserTierPolicyConfig.mock.calls[0][0].cultivation_ranks['筑基期'].benefits.flashback_bottles).toBe(11)
    expect(messageMocks.success).toHaveBeenCalledWith('等级权益已保存并生效')
  })
})
