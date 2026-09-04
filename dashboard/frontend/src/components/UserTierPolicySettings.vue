<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  CheckCircleOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'

import { fetchUserTierPolicyConfig, updateUserTierPolicyConfig } from '../api/api'

interface PriorityRule {
  daily_usage_lt: number | null
  priority: number
}

interface VideoPolicy {
  resolutions: string[]
  durations: string[]
}

interface RankPolicy {
  upgrade: { invitations: number; checkins: number; generations: number; channel_member: boolean }
  benefits: {
    checkin_enabled: boolean
    checkin_credits: number
    web_access: boolean
    flashback_bonus: number
    queue_pressure_exempt: boolean
  }
  video: VideoPolicy
  priority_rules: PriorityRule[]
}

interface IdentityPolicy {
  benefits: {
    mortal_checkin_access: boolean
    checkin_bonus: number
    web_access: boolean
    concurrent_tasks: number
    favorite_limit: number
    flashback_bonus: number
    queue_pressure_exempt: boolean
  }
  video: VideoPolicy
  priority_rules: PriorityRule[]
}

interface TierPolicyConfig {
  schema_version: 2
  capacity_combination_rule: 'additive'
  flashback_base: number
  cultivation_ranks: Record<string, RankPolicy>
  membership_identities: Record<string, IdentityPolicy>
  low_trust: {
    enabled: boolean
    checkin_threshold: number
    successful_order_exempt: boolean
    referral_count_threshold: number
    successful_invitee_rate_percent_threshold: number
    trusted_priority_bonus: number
    new_user_generation_threshold: number
    new_user_base_priority: number
  }
}

interface PolicyResponse {
  key: string
  config: TierPolicyConfig
  updated_at?: string | null
}

const RANKS = ['凡人', '练气期', '筑基期', '金丹期', '元婴期']
const IDENTITIES = ['外门弟子', '内门弟子', '核心弟子', '真传弟子']
const RESOLUTIONS = [
  { label: '512p', value: '512p', disabled: true },
  { label: '720p', value: '720p' },
  { label: '1024p', value: '1024p' },
]
const DURATIONS = [
  { label: '5s', value: '5s', disabled: true },
  { label: '8s', value: '8s' },
  { label: '10s', value: '10s' },
]

const activeTab = ref('cultivation')
const loading = ref(false)
const saving = ref(false)
const config = ref<TierPolicyConfig | null>(null)
const savedSnapshot = ref('')
const updatedAt = ref<string | null>(null)
const priorityEditor = ref<{ kind: 'rank' | 'identity'; key: string } | null>(null)

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const dirty = computed(() => config.value !== null && JSON.stringify(config.value) !== savedSnapshot.value)
const flashbackRange = computed(() => {
  if (!config.value) return '7–20'
  const rankBonuses = Object.values(config.value.cultivation_ranks).map(item => item.benefits.flashback_bonus)
  const identityBonuses = Object.values(config.value.membership_identities).map(item => item.benefits.flashback_bonus)
  const minimum = config.value.flashback_base + Math.min(...rankBonuses) + Math.min(...identityBonuses)
  const maximum = config.value.flashback_base + Math.max(...rankBonuses) + Math.max(...identityBonuses)
  return `${minimum}–${maximum}`
})
const currentPriorityRules = computed(() => {
  if (!config.value || !priorityEditor.value) return []
  const { kind, key } = priorityEditor.value
  return kind === 'rank'
    ? config.value.cultivation_ranks[key].priority_rules
    : config.value.membership_identities[key].priority_rules
})

const formatUpdatedAt = computed(() => {
  if (!updatedAt.value) return '尚未自定义，当前使用系统默认值'
  return `最近保存：${new Date(updatedAt.value).toLocaleString('zh-CN')}`
})

async function loadPolicy() {
  loading.value = true
  try {
    const response = await fetchUserTierPolicyConfig() as PolicyResponse
    config.value = clone(response.config)
    savedSnapshot.value = JSON.stringify(response.config)
    updatedAt.value = response.updated_at || null
  } catch (error) {
    console.error(error)
    message.error('等级权益配置加载失败')
  } finally {
    loading.value = false
  }
}

async function savePolicy() {
  if (!config.value) return
  saving.value = true
  try {
    const response = await updateUserTierPolicyConfig(config.value) as PolicyResponse
    config.value = clone(response.config)
    savedSnapshot.value = JSON.stringify(response.config)
    updatedAt.value = response.updated_at || null
    message.success('等级权益已保存并生效')
  } catch (error: any) {
    console.error(error)
    message.error(error?.response?.data?.detail || '保存失败，请检查参数后重试')
  } finally {
    saving.value = false
  }
}

function restoreSaved() {
  if (!savedSnapshot.value) return
  config.value = JSON.parse(savedSnapshot.value) as TierPolicyConfig
  message.success('已恢复到本次保存前的值')
}

function openPriority(kind: 'rank' | 'identity', key: string) {
  priorityEditor.value = { kind, key }
}

function addPriorityRule() {
  const rules = currentPriorityRules.value
  if (rules.length >= 4) return
  const previous = rules[rules.length - 1]?.daily_usage_lt
  rules.push({ daily_usage_lt: previous === null ? null : (previous || 0) + 20, priority: 1 })
}

function removePriorityRule(index: number) {
  currentPriorityRules.value.splice(index, 1)
}

onMounted(() => void loadPolicy())
</script>

<template>
  <div class="tier-policy-page" :class="{ loading }">
    <section class="policy-hero">
      <div class="hero-copy">
        <div class="hero-icon"><SafetyCertificateOutlined /></div>
        <div>
          <div class="hero-title-row">
            <h1>等级权益配置</h1>
            <span v-if="dirty" class="dirty-dot">有未保存修改</span>
          </div>
          <p>统一管理修为晋升、会员身份、低信任判定及用户权益。闪回瓶按基础容量、修为加成、身份加成相加，视频取可用并集。</p>
          <span class="updated-at">{{ formatUpdatedAt }}</span>
        </div>
      </div>
      <div class="hero-actions">
        <a-button :disabled="!dirty" @click="restoreSaved"><ReloadOutlined />撤销修改</a-button>
        <a-button type="primary" :loading="saving" :disabled="!dirty" @click="savePolicy"><SaveOutlined />保存并生效</a-button>
      </div>
    </section>

    <section class="summary-grid">
      <div class="summary-card"><HistoryOutlined /><div><a-input-number v-if="config" v-model:value="config.flashback_base" :min="1" :max="100" size="small" /><strong v-else>5</strong><span>闪回瓶基础容量</span></div></div>
      <div class="summary-card"><ThunderboltOutlined /><div><strong>{{ flashbackRange }}</strong><span>叠加后的实际容量范围</span></div></div>
      <div class="summary-card"><CheckCircleOutlined /><div><strong>叠加计算</strong><span>基础 + 修为加成 + 身份加成</span></div></div>
    </section>

    <a-tabs v-if="config" v-model:active-key="activeTab" class="policy-tabs">
      <a-tab-pane key="cultivation" tab="修为升级与权益">
        <div class="section-note">晋升条件均为“同时满足”。修为栏配置闪回瓶加成，凡人加成为 0；未知历史高阶修为按元婴期权益处理。</div>
        <div class="table-shell">
          <table class="policy-table rank-table">
            <thead><tr><th>修为</th><th>升级条件</th><th>签到</th><th>闪回瓶加成</th><th>访问与队列</th><th>视频权益</th><th>优先级</th></tr></thead>
            <tbody>
              <tr v-for="rank in RANKS" :key="rank">
                <td><span class="tier-name">{{ rank }}</span></td>
                <td>
                  <div v-if="rank !== '凡人'" class="inline-fields">
                    <label>邀请<a-input-number v-model:value="config.cultivation_ranks[rank].upgrade.invitations" :min="0" :max="1000000" size="small" /></label>
                    <label>签到<a-input-number v-model:value="config.cultivation_ranks[rank].upgrade.checkins" :min="0" :max="1000000" size="small" /></label>
                    <label>生成<a-input-number v-model:value="config.cultivation_ranks[rank].upgrade.generations" :min="0" :max="10000000" size="small" /></label>
                    <label class="switch-label">需入频道<a-switch v-model:checked="config.cultivation_ranks[rank].upgrade.channel_member" size="small" /></label>
                  </div>
                  <span v-else class="muted">初始修为</span>
                </td>
                <td><div class="stack-fields"><a-switch v-model:checked="config.cultivation_ranks[rank].benefits.checkin_enabled" checked-children="可签" un-checked-children="禁用" /><label>基础灵石<a-input-number v-model:value="config.cultivation_ranks[rank].benefits.checkin_credits" :min="0" :max="10000" size="small" /></label></div></td>
                <td><a-input-number v-model:value="config.cultivation_ranks[rank].benefits.flashback_bonus" :min="0" :max="100" /></td>
                <td><div class="switch-stack"><label>Web <a-switch v-model:checked="config.cultivation_ranks[rank].benefits.web_access" size="small" /></label><label>高压豁免 <a-switch v-model:checked="config.cultivation_ranks[rank].benefits.queue_pressure_exempt" size="small" /></label></div></td>
                <td><a-checkbox-group v-model:value="config.cultivation_ranks[rank].video.resolutions" :options="RESOLUTIONS" /><a-checkbox-group v-model:value="config.cultivation_ranks[rank].video.durations" :options="DURATIONS" /></td>
                <td><a-button size="small" @click="openPriority('rank', rank)">编辑 {{ config.cultivation_ranks[rank].priority_rules.length }} 档</a-button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </a-tab-pane>

      <a-tab-pane key="identity" tab="身份权益">
        <div class="section-note">身份栏配置闪回瓶加成，并与基础容量、当前修为加成叠加；身份到期会自动回落为外门弟子。</div>
        <div class="table-shell">
          <table class="policy-table identity-table">
            <thead><tr><th>身份</th><th>签到加成</th><th>并发</th><th>收藏</th><th>闪回瓶加成</th><th>访问与队列</th><th>视频权益</th><th>优先级</th></tr></thead>
            <tbody>
              <tr v-for="identity in IDENTITIES" :key="identity">
                <td><span class="tier-name identity">{{ identity }}</span></td>
                <td><div class="stack-fields"><label>加成<a-input-number v-model:value="config.membership_identities[identity].benefits.checkin_bonus" :min="0" :max="10000" size="small" /></label><label>凡人可签 <a-switch v-model:checked="config.membership_identities[identity].benefits.mortal_checkin_access" size="small" /></label></div></td>
                <td><a-input-number v-model:value="config.membership_identities[identity].benefits.concurrent_tasks" :min="1" :max="100" /></td>
                <td><a-input-number v-model:value="config.membership_identities[identity].benefits.favorite_limit" :min="1" :max="100000" /></td>
                <td><a-input-number v-model:value="config.membership_identities[identity].benefits.flashback_bonus" :min="0" :max="100" /></td>
                <td><div class="switch-stack"><label>Web <a-switch v-model:checked="config.membership_identities[identity].benefits.web_access" size="small" /></label><label>高压豁免 <a-switch v-model:checked="config.membership_identities[identity].benefits.queue_pressure_exempt" size="small" /></label></div></td>
                <td><a-checkbox-group v-model:value="config.membership_identities[identity].video.resolutions" :options="RESOLUTIONS" /><a-checkbox-group v-model:value="config.membership_identities[identity].video.durations" :options="DURATIONS" /></td>
                <td><a-button size="small" @click="openPriority('identity', identity)">编辑 {{ config.membership_identities[identity].priority_rules.length }} 档</a-button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </a-tab-pane>

      <a-tab-pane key="trust" tab="低信任规则">
        <div class="trust-head"><div><h2>低信任免费层判定</h2><p>超过签到阈值且没有成功订单、也未达到高质量邀请豁免时，取消可信用户优先级加成。</p></div><a-switch v-model:checked="config.low_trust.enabled" checked-children="启用" un-checked-children="停用" /></div>
        <div class="trust-grid" :class="{ disabled: !config.low_trust.enabled }">
          <label class="field-card"><span>签到次数阈值</span><small>超过该值开始进行低信任检查</small><a-input-number v-model:value="config.low_trust.checkin_threshold" :min="0" :max="100000" /></label>
          <label class="field-card"><span>邀请人数豁免门槛</span><small>邀请人数需严格超过该值</small><a-input-number v-model:value="config.low_trust.referral_count_threshold" :min="0" :max="1000000" /></label>
          <label class="field-card"><span>成功受邀人比例</span><small>成功下单受邀人占比需严格超过</small><a-input-number v-model:value="config.low_trust.successful_invitee_rate_percent_threshold" :min="0" :max="100" addon-after="%" /></label>
          <label class="field-card"><span>可信优先级加成</span><small>非低信任用户统一获得</small><a-input-number v-model:value="config.low_trust.trusted_priority_bonus" :min="0" :max="500" /></label>
          <label class="field-card"><span>新用户生成阈值</span><small>低于该生成次数使用新用户优先级</small><a-input-number v-model:value="config.low_trust.new_user_generation_threshold" :min="0" :max="10000" /></label>
          <label class="field-card"><span>新用户基础优先级</span><small>与可信加成组合后进入队列</small><a-input-number v-model:value="config.low_trust.new_user_base_priority" :min="0" :max="500" /></label>
          <label class="field-card switch-card"><span>成功订单自动豁免</span><small>含正常支付、人工与赠送成功订单</small><a-switch v-model:checked="config.low_trust.successful_order_exempt" /></label>
        </div>
      </a-tab-pane>
    </a-tabs>

    <a-drawer :open="!!priorityEditor" width="440" title="每日用量优先级" @close="priorityEditor = null">
      <p class="drawer-note">按每日用量从小到大匹配；阈值留空表示兜底档。最多 4 档。</p>
      <div v-for="(rule, index) in currentPriorityRules" :key="index" class="priority-row">
        <span>用量 &lt;</span><a-input-number v-model:value="rule.daily_usage_lt" :min="1" :max="100000" placeholder="兜底" /><span>优先级</span><a-input-number v-model:value="rule.priority" :min="0" :max="500" /><a-button danger type="text" @click="removePriorityRule(index)">删除</a-button>
      </div>
      <a-button block :disabled="currentPriorityRules.length >= 4 || currentPriorityRules[currentPriorityRules.length - 1]?.daily_usage_lt === null" @click="addPriorityRule">增加一档</a-button>
    </a-drawer>
  </div>
</template>

<style scoped>
.tier-policy-page { min-height: 100%; padding: 22px; background: #f4f7fb; color: #172033; transition: opacity .2s; }.tier-policy-page.loading { opacity: .62; pointer-events: none; }
.policy-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 24px 26px; background: linear-gradient(120deg, #071c31 0%, #123e63 65%, #146e86 100%); border-radius: 18px; color: white; box-shadow: 0 12px 30px rgba(9, 35, 60, .16); }
.hero-copy { display: flex; gap: 16px; align-items: flex-start; }.hero-icon { display: grid; place-items: center; flex: 0 0 46px; height: 46px; border-radius: 13px; font-size: 23px; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.16); }
.hero-title-row { display: flex; align-items: center; gap: 12px; }.hero-title-row h1 { margin: 0; color: white; font-size: 24px; }.hero-copy p { margin: 7px 0 5px; color: #d7e8f3; }.updated-at { color: #9dc4d5; font-size: 12px; }.dirty-dot { padding: 3px 9px; border-radius: 20px; color: #ffe4a3; background: rgba(251, 191, 36, .16); font-size: 12px; }.hero-actions { display: flex; gap: 10px; flex-shrink: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 16px 0; }.summary-card { display: flex; align-items: center; gap: 13px; padding: 15px 18px; border: 1px solid #e6edf4; border-radius: 14px; background: white; color: #2581a0; }.summary-card :deep(svg) { font-size: 22px; }.summary-card div { display: flex; flex-direction: column; }.summary-card strong { color: #172033; font-size: 17px; }.summary-card span { color: #78869a; font-size: 12px; }
.policy-tabs { padding: 4px 20px 22px; border: 1px solid #e4ebf3; border-radius: 16px; background: white; }.section-note { margin: 2px 0 16px; padding: 10px 13px; color: #52677d; border-left: 3px solid #22a6c3; border-radius: 5px; background: #f0f8fa; font-size: 13px; }.table-shell { overflow-x: auto; border: 1px solid #e7edf3; border-radius: 12px; }.policy-table { width: 100%; min-width: 1200px; border-collapse: collapse; }.policy-table th { padding: 12px; color: #66778b; background: #f7f9fc; font-size: 12px; text-align: left; white-space: nowrap; }.policy-table td { padding: 14px 12px; border-top: 1px solid #edf1f5; vertical-align: top; }.policy-table tr:hover td { background: #fbfdff; }.tier-name { display: inline-block; padding: 5px 10px; border-radius: 8px; color: #096b86; background: #e8f7fa; font-weight: 600; white-space: nowrap; }.tier-name.identity { color: #7c5a10; background: #fff5d8; }.muted { color: #98a3b1; }.inline-fields { display: grid; grid-template-columns: repeat(3, 78px); gap: 7px; }.inline-fields label,.stack-fields label { display: flex; flex-direction: column; gap: 4px; color: #78869a; font-size: 11px; }.inline-fields .switch-label { grid-column: 1 / -1; flex-direction: row; align-items: center; }.stack-fields,.switch-stack { display: flex; flex-direction: column; gap: 8px; }.switch-stack label { display: flex; align-items: center; justify-content: space-between; gap: 8px; white-space: nowrap; color: #617287; font-size: 12px; }.policy-table :deep(.ant-checkbox-group) { display: flex; flex-wrap: nowrap; margin-bottom: 7px; white-space: nowrap; }.policy-table :deep(.ant-checkbox-wrapper) { margin-inline-start: 0; margin-inline-end: 8px; font-size: 12px; }
.trust-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; margin: 4px 0 18px; }.trust-head h2 { margin: 0 0 4px; font-size: 18px; }.trust-head p { margin: 0; color: #718096; }.trust-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; transition: opacity .2s; }.trust-grid.disabled { opacity: .48; }.field-card { display: flex; flex-direction: column; gap: 7px; padding: 17px; border: 1px solid #e7edf3; border-radius: 12px; background: #fbfcfe; }.field-card span { font-weight: 600; }.field-card small { min-height: 34px; color: #8290a2; }.switch-card :deep(.ant-switch) { align-self: flex-start; }
.drawer-note { color: #718096; }.priority-row { display: grid; grid-template-columns: auto 105px auto 90px auto; gap: 7px; align-items: center; margin-bottom: 10px; font-size: 12px; }
@media (max-width: 900px) { .tier-policy-page { padding: 12px; }.policy-hero { align-items: stretch; flex-direction: column; padding: 19px; }.hero-actions { justify-content: flex-end; }.summary-grid,.trust-grid { grid-template-columns: 1fr; }.summary-grid { gap: 8px; }.policy-tabs { padding-inline: 12px; }.hero-copy p { font-size: 13px; } }
</style>
