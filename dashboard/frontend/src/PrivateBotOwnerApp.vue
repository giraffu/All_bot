<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  KeyOutlined,
  LogoutOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'

import QqccBotSettings from './components/QqccBotSettings.vue'
import {
  exchangePrivateBotOwnerTicket,
  fetchPrivateBotOwnerMe,
  pausePrivateBotOwner,
  resumePrivateBotOwner,
  retryPrivateBotOwner,
  updatePrivateBotOwnerConfig,
  updatePrivateBotOwnerCredentials,
  uploadPrivateBotOwnerDemoMedia,
  generatePrivateBotOwnerDemoMedia,
  getPrivateBotOwnerDemoGeneration,
} from './api/privateBotOwnerApi'
import type { PrivateBotOwnerMeResponse } from './api/privateBotOwnerApi'
import { usePrivateBotOwnerAuth } from './composables/usePrivateBotOwnerAuth'

type AuthPhase = 'initializing' | 'ready' | 'missing-ticket' | 'error'

const { getAuthToken, setAuthToken, clearAuthToken } = usePrivateBotOwnerAuth()
const authPhase = ref<AuthPhase>('initializing')
const authError = ref('')
const ownerData = ref<PrivateBotOwnerMeResponse | null>(null)
const loadingOwner = ref(false)
const runningAction = ref('')
const credentialToken = ref('')

const consumeTicketFromUrl = () => {
  if (typeof window === 'undefined') return null
  const url = new URL(window.location.href)
  const fragmentParams = new URLSearchParams(url.hash.replace(/^#/, ''))
  const ticket = fragmentParams.get('ticket')
  const hasQueryTicket = url.searchParams.has('ticket')
  if (!ticket && !hasQueryTicket) return null
  fragmentParams.delete('ticket')
  url.searchParams.delete('ticket')
  const cleanFragment = fragmentParams.toString()
  const cleanUrl = `${url.pathname}${url.search}${cleanFragment ? `#${cleanFragment}` : ''}`
  window.history.replaceState(window.history.state, document.title, cleanUrl)
  return ticket
}

let initialTicket: string | null = consumeTicketFromUrl()

const bot = computed(() => ownerData.value?.bot ?? null)
const username = computed(() => bot.value?.telegram_username?.replace(/^@/, '') || '')
const botUrl = computed(() => (username.value ? `https://t.me/${username.value}` : ''))

const runtimeLabels = {
  provisioning: '接入中',
  active: '运行中',
  paused: '已暂停',
  disabled: '已禁用',
  error: '接入异常',
} as const

const runtimeColors = {
  provisioning: 'processing',
  active: 'success',
  paused: 'warning',
  disabled: 'default',
  error: 'error',
} as const

const runtimeLabel = computed(() =>
  bot.value ? runtimeLabels[bot.value.runtime_status] : '加载中',
)

const runtimeColor = computed(() =>
  bot.value ? runtimeColors[bot.value.runtime_status] : 'default',
)

const formatDate = (value: string | null | undefined) => {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN')
}

const applyOwnerData = (payload: PrivateBotOwnerMeResponse) => {
  ownerData.value = payload
}

const loadOwner = async () => {
  loadingOwner.value = true
  try {
    const payload = await fetchPrivateBotOwnerMe()
    applyOwnerData(payload)
    return payload
  } finally {
    loadingOwner.value = false
  }
}

const initialize = async () => {
  try {
    if (initialTicket) {
      const ticket = initialTicket
      initialTicket = null
      const exchanged = await exchangePrivateBotOwnerTicket(ticket)
      setAuthToken(exchanged.access_token)
    } else if (!getAuthToken()) {
      authPhase.value = 'missing-ticket'
      return
    }
    await loadOwner()
    authPhase.value = 'ready'
  } catch {
    clearAuthToken()
    authError.value = '管理链接无效或已过期，请回到官方懒人 Bot 重新获取。'
    authPhase.value = 'error'
  } finally {
    initialTicket = null
  }
}

const refreshOwner = async () => {
  try {
    await loadOwner()
    message.success('Bot 状态已刷新')
  } catch {
    message.error('刷新 Bot 状态失败')
  }
}

const fetchOwnerConfig = async () => {
  const payload = await loadOwner()
  return {
    key: `qqcc_private_bot_config:${payload.bot.id}`,
    updated_at: payload.bot.updated_at,
    config: payload.config,
    options: payload.options,
  }
}

const saveOwnerConfig = async (config: unknown) => {
  if (!ownerData.value) throw new Error('owner data is not loaded')
  const payload = await updatePrivateBotOwnerConfig({
    config_version: ownerData.value.config_version,
    config,
  })
  applyOwnerData(payload)
  return {
    key: `qqcc_private_bot_config:${payload.bot.id}`,
    updated_at: payload.bot.updated_at,
    config: payload.config,
    options: payload.options,
  }
}

const runBotAction = async (
  action: 'pause' | 'resume' | 'retry',
  request: () => Promise<PrivateBotOwnerMeResponse>,
) => {
  runningAction.value = action
  try {
    const mutationPayload = await request()
    applyOwnerData(mutationPayload)
    const refreshedPayload = await loadOwner()
    const mutationFailed = mutationPayload.bot.runtime_status === 'error'
      || refreshedPayload.bot.runtime_status === 'error'
    if (mutationFailed) {
      const labels = {
        pause: '暂停操作返回异常状态，请查看健康信息',
        resume: '恢复未完成，Telegram 接入仍然异常',
        retry: '重新接入未完成，请查看健康信息后重试',
      }
      message.error(labels[action])
      return
    }
    if (
      (action === 'resume' || action === 'retry')
      && refreshedPayload.bot.runtime_status !== 'active'
    ) {
      message.warning(
        refreshedPayload.bot.runtime_status === 'disabled'
          ? '恢复请求已处理，但管理员禁用仍在生效'
          : '恢复请求已处理，但 Bot 当前尚未运行',
      )
      return
    }
    const labels = { pause: '已暂停接收新任务', resume: '私有 Bot 已恢复', retry: '已重新接入 Telegram' }
    message.success(labels[action])
  } catch {
    const labels = { pause: '暂停失败', resume: '恢复失败', retry: '重新接入失败' }
    message.error(labels[action])
  } finally {
    runningAction.value = ''
  }
}

const submitCredentials = async () => {
  const token = credentialToken.value.trim()
  if (!token) {
    message.error('请输入 Bot token')
    return
  }
  credentialToken.value = ''
  runningAction.value = 'credentials'
  try {
    const mutationPayload = await updatePrivateBotOwnerCredentials(token)
    applyOwnerData(mutationPayload)
    const refreshedPayload = await loadOwner()
    if (
      mutationPayload.bot.runtime_status === 'error'
      || refreshedPayload.bot.runtime_status === 'error'
    ) {
      message.warning('Bot token 已更新，但 Telegram 接入仍然异常，请重试接入')
      return
    }
    message.success('Bot token 已安全更新')
  } catch {
    message.error('token 更新失败，请确认它属于当前 Bot 且未被其他系统使用')
  } finally {
    runningAction.value = ''
  }
}

const logout = () => {
  clearAuthToken()
  ownerData.value = null
  authPhase.value = 'missing-ticket'
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <main class="private-owner-shell">
    <div v-if="authPhase === 'initializing'" class="private-owner-state">
      <div class="private-owner-logo"><RobotOutlined /></div>
      <a-spin size="large" />
      <h1>正在安全登录</h1>
      <p>管理凭据仅保存在当前浏览器会话。</p>
    </div>

    <div v-else-if="authPhase !== 'ready'" class="private-owner-state">
      <div class="private-owner-logo"><KeyOutlined /></div>
      <h1>需要新的管理链接</h1>
      <p>{{ authError || '请从官方 QQCC 懒人 Bot 的“私有bot”入口打开管理后台。' }}</p>
      <a-alert
        type="info"
        show-icon
        message="为了保护你的 Bot，管理链接只能使用一次，并会在 5 分钟后过期。"
      />
    </div>

    <template v-else-if="ownerData && bot">
      <header class="private-owner-header">
        <div class="private-owner-brand">
          <div class="private-owner-logo"><RobotOutlined /></div>
          <div>
            <div class="private-owner-eyebrow">QQCC PRIVATE BOT</div>
            <h1>{{ bot.telegram_display_name || '我的私有 Bot' }}</h1>
          </div>
        </div>
        <div class="private-owner-header__actions">
          <a-button :loading="loadingOwner" @click="refreshOwner">
            <template #icon><ReloadOutlined /></template>
            刷新状态
          </a-button>
          <a-button @click="logout">
            <template #icon><LogoutOutlined /></template>
            退出
          </a-button>
        </div>
      </header>

      <div class="private-owner-content">
        <section class="private-owner-overview">
          <div class="private-owner-overview__identity">
            <div>
              <span class="private-owner-overview__caption">YOUR BOT</span>
              <h2>{{ username ? `@${username}` : `Bot ${bot.telegram_bot_id}` }}</h2>
              <a v-if="botUrl" :href="botUrl" target="_blank" rel="noreferrer">打开 Telegram Bot ↗</a>
              <span v-else>Telegram ID {{ bot.telegram_bot_id }}</span>
            </div>
            <a-tag :color="runtimeColor" class="private-owner-status">{{ runtimeLabel }}</a-tag>
          </div>

          <div class="private-owner-overview__facts">
            <div>
              <span>配置版本</span>
              <strong>v{{ ownerData.config_version }}</strong>
            </div>
            <div>
              <span>最近 Webhook</span>
              <strong>{{ formatDate(bot.last_webhook_at) }}</strong>
            </div>
            <div>
              <span>最近 Update</span>
              <strong>{{ formatDate(bot.last_update_at) }}</strong>
            </div>
          </div>

          <a-alert
            v-if="!bot.admin_enabled"
            type="error"
            show-icon
            message="此 Bot 已被管理员禁用"
            description="你可以查看和编辑配置，但无法自行恢复运行。"
          />
          <a-alert
            v-else-if="bot.last_error_code || bot.last_error_message"
            type="warning"
            show-icon
            :message="bot.last_error_code || 'Telegram 接入异常'"
            :description="bot.last_error_message || '请尝试重新接入，或更新当前 Bot 的 token。'"
          />

          <div class="private-owner-overview__actions">
            <a-button
              v-if="bot.owner_enabled"
              :loading="runningAction === 'pause'"
              @click="runBotAction('pause', pausePrivateBotOwner)"
            >
              <template #icon><PauseCircleOutlined /></template>
              暂停接收新任务
            </a-button>
            <a-button
              v-else
              type="primary"
              :disabled="!bot.admin_enabled"
              :loading="runningAction === 'resume'"
              data-testid="owner-resume-bot"
              @click="runBotAction('resume', resumePrivateBotOwner)"
            >
              <template #icon><PlayCircleOutlined /></template>
              恢复运行
            </a-button>
            <a-button
              v-if="bot.runtime_status === 'error' || bot.runtime_status === 'provisioning'"
              :disabled="!bot.admin_enabled || !bot.owner_enabled"
              :loading="runningAction === 'retry'"
              data-testid="owner-retry-bot"
              @click="runBotAction('retry', retryPrivateBotOwner)"
            >
              <template #icon><SyncOutlined /></template>
              重试接入
            </a-button>
          </div>
        </section>

        <section class="private-owner-credentials">
          <div>
            <span class="private-owner-overview__caption">TOKEN ROTATION</span>
            <h2>更新 Bot token</h2>
            <p>仅允许更新当前 Telegram Bot 的 token。提交后输入框会立即清空，后台不会展示明文。</p>
          </div>
          <div class="private-owner-credentials__form">
            <a-input-password
              v-model:value="credentialToken"
              autocomplete="new-password"
              placeholder="123456789:AA..."
              data-testid="owner-credential-token"
              @press-enter="submitCredentials"
            />
            <a-button
              type="primary"
              :loading="runningAction === 'credentials'"
              data-testid="owner-update-credentials"
              @click="submitCredentials"
            >
              更新 token
            </a-button>
          </div>
        </section>

        <qqcc-bot-settings
          :fetch-config="fetchOwnerConfig"
          :update-config="saveOwnerConfig"
          :upload-demo-media="uploadPrivateBotOwnerDemoMedia"
          :generate-demo-media="generatePrivateBotOwnerDemoMedia"
          :get-demo-generation="getPrivateBotOwnerDemoGeneration"
          :demo-media-object-prefixes="[
            `qqcc/private/${bot.id}/demo`,
          ]"
        />
      </div>
    </template>
  </main>
</template>

<style scoped>
:global(html),
:global(body),
:global(#app) {
  width: 100%;
  min-width: 320px;
  min-height: 100%;
  margin: 0;
}

:global(body) {
  background: #eef3f8;
  color: #0f172a;
}

.private-owner-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 85% 0%, rgba(20, 184, 166, 0.15), transparent 28%),
    radial-gradient(circle at 10% 5%, rgba(37, 99, 235, 0.13), transparent 30%),
    linear-gradient(180deg, #f8fafc 0%, #eef3f8 100%);
}

.private-owner-header {
  position: sticky;
  z-index: 20;
  top: 0;
  display: flex;
  min-height: 68px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 24px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.8);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 16px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(12px);
}

.private-owner-brand,
.private-owner-header__actions,
.private-owner-overview__identity,
.private-owner-overview__actions,
.private-owner-credentials__form {
  display: flex;
  align-items: center;
  gap: 12px;
}

.private-owner-logo {
  display: inline-flex;
  width: 42px;
  height: 42px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: #ffffff;
  background: linear-gradient(135deg, #0f172a, #2563eb 58%, #14b8a6);
  box-shadow: 0 9px 24px rgba(37, 99, 235, 0.25);
  font-size: 20px;
}

.private-owner-brand h1,
.private-owner-overview h2,
.private-owner-credentials h2 {
  margin: 0;
  color: #0f172a;
}

.private-owner-brand h1 {
  font-size: 17px;
}

.private-owner-eyebrow,
.private-owner-overview__caption {
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

.private-owner-content {
  display: flex;
  width: min(1480px, calc(100% - 40px));
  margin: 0 auto;
  flex-direction: column;
  gap: 20px;
  padding: 24px 0 40px;
}

.private-owner-overview,
.private-owner-credentials {
  border: 1px solid #dbe4ef;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.private-owner-overview {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 22px;
}

.private-owner-overview__identity {
  justify-content: space-between;
}

.private-owner-overview__identity h2 {
  margin: 4px 0;
  font-size: 23px;
}

.private-owner-status {
  margin: 0;
  padding: 5px 13px;
  border-radius: 999px;
  font-size: 13px;
}

.private-owner-overview__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.private-owner-overview__facts > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  padding: 13px 15px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.private-owner-overview__facts span {
  color: #64748b;
  font-size: 12px;
}

.private-owner-overview__facts strong {
  overflow: hidden;
  color: #334155;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.private-owner-overview__actions {
  flex-wrap: wrap;
}

.private-owner-credentials {
  display: grid;
  grid-template-columns: minmax(260px, 0.85fr) minmax(320px, 1.15fr);
  align-items: center;
  gap: 24px;
  padding: 20px 22px;
}

.private-owner-credentials h2 {
  margin-top: 4px;
  font-size: 17px;
}

.private-owner-credentials p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.private-owner-credentials__form :deep(.ant-input-affix-wrapper) {
  flex: 1;
}

.private-owner-state {
  display: flex;
  width: min(440px, calc(100% - 32px));
  min-height: 100vh;
  margin: 0 auto;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 15px;
  text-align: center;
}

.private-owner-state h1 {
  margin: 4px 0 0;
  font-size: 24px;
}

.private-owner-state p {
  margin: 0;
  color: #64748b;
}

@media (max-width: 760px) {
  .private-owner-header {
    padding: 10px 12px;
  }

  .private-owner-header__actions :deep(.ant-btn:first-child) {
    display: none;
  }

  .private-owner-content {
    width: calc(100% - 24px);
    padding-top: 12px;
  }

  .private-owner-overview__facts,
  .private-owner-credentials {
    grid-template-columns: minmax(0, 1fr);
  }

  .private-owner-credentials__form {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
