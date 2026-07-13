<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  DeleteOutlined,
  EyeOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'

import {
  deletePrivateBotAdmin,
  disablePrivateBotAdmin,
  enablePrivateBotAdmin,
  fetchPrivateBotAdminDetail,
  fetchPrivateBotsAdmin,
} from '../api/qqccConfigApi'
import type {
  PrivateBotAdminDetail,
  PrivateBotAdminListItem,
  PrivateBotConfigPayload,
  PrivateBotRuntimeStatus,
} from '../api/qqccConfigApi'

const pageSize = 20
const loading = ref(false)
const detailLoading = ref(false)
const actionBotId = ref<number | null>(null)
const items = ref<PrivateBotAdminListItem[]>([])
const total = ref(0)
const page = ref(1)
const ownerQuery = ref('')
const usernameQuery = ref('')
const statusQuery = ref<PrivateBotRuntimeStatus | undefined>()
const adminStateQuery = ref<'enabled' | 'disabled' | undefined>()
const detail = ref<PrivateBotAdminDetail | null>(null)
const detailOpen = ref(false)

const rangeText = computed(() => {
  if (total.value === 0) return '暂无私有 Bot'
  const start = (page.value - 1) * pageSize + 1
  const end = Math.min(page.value * pageSize, total.value)
  return `第 ${start}-${end} 项，共 ${total.value} 项`
})

const statusLabels: Record<PrivateBotRuntimeStatus, string> = {
  provisioning: '接入中',
  active: '运行中',
  paused: '已暂停',
  disabled: '已禁用',
  error: '异常',
}

const statusColors: Record<PrivateBotRuntimeStatus, string> = {
  provisioning: 'processing',
  active: 'success',
  paused: 'warning',
  disabled: 'default',
  error: 'error',
}

const formatDate = (value: string | null) => {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN')
}

const botLabel = (bot: PrivateBotAdminListItem) =>
  bot.telegram_username ? `@${bot.telegram_username.replace(/^@/, '')}` : `Bot ${bot.telegram_bot_id}`

const ownerLabel = (bot: PrivateBotAdminListItem) =>
  bot.owner.full_name || bot.owner.username || `用户 ${bot.owner.id}`

const loadBots = async () => {
  loading.value = true
  try {
    const payload = await fetchPrivateBotsAdmin({
      page: page.value,
      page_size: pageSize,
      status: statusQuery.value,
      admin_enabled:
        adminStateQuery.value === undefined
          ? undefined
          : adminStateQuery.value === 'enabled',
      owner: ownerQuery.value.trim() || undefined,
      username: usernameQuery.value.trim().replace(/^@/, '') || undefined,
    })
    items.value = payload.items
    total.value = payload.total
    page.value = payload.page
    return true
  } catch {
    message.error('加载私有 Bot 列表失败')
    return false
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  page.value = 1
  void loadBots()
}

const resetFilters = () => {
  ownerQuery.value = ''
  usernameQuery.value = ''
  statusQuery.value = undefined
  adminStateQuery.value = undefined
  page.value = 1
  void loadBots()
}

const changePage = (nextPage: number) => {
  page.value = nextPage
  void loadBots()
}

const openDetail = async (botId: number) => {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await fetchPrivateBotAdminDetail(botId)
  } catch {
    detailOpen.value = false
    message.error('加载私有 Bot 详情失败')
  } finally {
    detailLoading.value = false
  }
}

const refreshDetailIfOpen = async (botId: number) => {
  if (detailOpen.value && detail.value?.id === botId) {
    detail.value = await fetchPrivateBotAdminDetail(botId)
  }
}

const applyMutationPayload = (payload: PrivateBotConfigPayload) => {
  items.value = items.value.map(item => (
    item.id === payload.bot.id ? { ...item, ...payload.bot } : item
  ))
  if (detail.value?.id === payload.bot.id) {
    detail.value = {
      ...detail.value,
      ...payload.bot,
      config: payload.config,
      config_version: payload.config_version,
      options: payload.options,
    }
  }
}

const setAdminEnabled = async (bot: PrivateBotAdminListItem, enabled: boolean) => {
  actionBotId.value = bot.id
  try {
    const mutationPayload = enabled
      ? await enablePrivateBotAdmin(bot.id)
      : await disablePrivateBotAdmin(bot.id)
    applyMutationPayload(mutationPayload)
    const [listRefreshed] = await Promise.all([loadBots(), refreshDetailIfOpen(bot.id)])
    if (!listRefreshed) return
    if (mutationPayload.bot.runtime_status === 'error') {
      message.error('管理员恢复已记录，但 Telegram 接入仍然异常')
      return
    }
    if (enabled && mutationPayload.bot.runtime_status !== 'active') {
      message.warning(
        mutationPayload.bot.runtime_status === 'paused'
          ? '管理员禁用已解除，Bot 仍处于主人暂停状态'
          : '管理员恢复已记录，但 Bot 当前尚未运行',
      )
      return
    }
    message.success(enabled ? '私有 Bot 已恢复' : '私有 Bot 已禁用')
  } catch {
    message.error(enabled ? '恢复私有 Bot 失败' : '禁用私有 Bot 失败')
  } finally {
    actionBotId.value = null
  }
}

const permanentlyUnbind = async (bot: PrivateBotAdminListItem) => {
  actionBotId.value = bot.id
  try {
    await deletePrivateBotAdmin(bot.id)
    if (detail.value?.id === bot.id) {
      detailOpen.value = false
      detail.value = null
    }
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await loadBots()
    message.success('私有 Bot 已永久解绑')
  } catch {
    message.error('永久解绑失败，请稍后重试')
  } finally {
    actionBotId.value = null
  }
}

onMounted(() => {
  void loadBots()
})
</script>

<template>
  <section class="private-bot-admin" data-testid="private-bot-admin-manager">
    <div class="private-bot-admin__hero">
      <div>
        <div class="private-bot-admin__eyebrow">MULTI-TENANT CONTROL</div>
        <h2>私有 Bot 管理</h2>
        <p>查看租户配置和运行健康，处理禁用、恢复与永久解绑。</p>
      </div>
      <a-button :loading="loading" @click="loadBots">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </div>

    <div class="private-bot-admin__filters">
      <a-input
        v-model:value="ownerQuery"
        allow-clear
        placeholder="Owner ID / Telegram ID / 用户名"
        data-testid="private-bot-owner-filter"
        @press-enter="applyFilters"
      />
      <a-input
        v-model:value="usernameQuery"
        allow-clear
        placeholder="Bot username"
        data-testid="private-bot-username-filter"
        @press-enter="applyFilters"
      />
      <a-select
        v-model:value="statusQuery"
        allow-clear
        placeholder="全部运行状态"
        data-testid="private-bot-status-filter"
      >
        <a-select-option v-for="(label, value) in statusLabels" :key="value" :value="value">
          {{ label }}
        </a-select-option>
      </a-select>
      <a-select
        v-model:value="adminStateQuery"
        allow-clear
        placeholder="全部管理状态"
        data-testid="private-bot-admin-state-filter"
      >
        <a-select-option value="enabled">管理员启用</a-select-option>
        <a-select-option value="disabled">管理员禁用</a-select-option>
      </a-select>
      <div class="private-bot-admin__filter-actions">
        <a-button type="primary" data-testid="private-bot-search" @click="applyFilters">查询</a-button>
        <a-button @click="resetFilters">重置</a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div v-if="items.length" class="private-bot-admin__table-wrap">
        <table class="private-bot-admin__table">
          <thead>
            <tr>
              <th>私有 Bot</th>
              <th>Owner</th>
              <th>运行状态</th>
              <th>健康信息</th>
              <th>更新时间</th>
              <th class="private-bot-admin__actions-heading">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bot in items" :key="bot.id" :data-testid="`private-bot-row-${bot.id}`">
              <td>
                <button class="private-bot-admin__bot-link" type="button" @click="openDetail(bot.id)">
                  {{ botLabel(bot) }}
                </button>
                <div class="private-bot-admin__muted">{{ bot.telegram_display_name || '未设置名称' }}</div>
                <div class="private-bot-admin__muted">ID {{ bot.telegram_bot_id }}</div>
              </td>
              <td>
                <div class="private-bot-admin__strong">{{ ownerLabel(bot) }}</div>
                <div class="private-bot-admin__muted">
                  #{{ bot.owner.id }} · TG {{ bot.owner.telegram_id }}
                </div>
              </td>
              <td>
                <div class="private-bot-admin__tag-row">
                  <a-tag :color="statusColors[bot.runtime_status]">
                    {{ statusLabels[bot.runtime_status] }}
                  </a-tag>
                  <a-tag :color="bot.admin_enabled ? 'blue' : 'red'">
                    {{ bot.admin_enabled ? '管理启用' : '管理禁用' }}
                  </a-tag>
                  <a-tag v-if="!bot.owner_enabled" color="warning">主人暂停</a-tag>
                </div>
              </td>
              <td>
                <div v-if="bot.last_error_code" class="private-bot-admin__error-code">
                  {{ bot.last_error_code }}
                </div>
                <div class="private-bot-admin__muted private-bot-admin__health-message">
                  {{ bot.last_error_message || '运行正常' }}
                </div>
              </td>
              <td>
                <div>{{ formatDate(bot.updated_at) }}</div>
                <div class="private-bot-admin__muted">Update {{ formatDate(bot.last_update_at) }}</div>
              </td>
              <td>
                <div class="private-bot-admin__row-actions">
                  <a-button size="small" @click="openDetail(bot.id)">
                    <template #icon><EyeOutlined /></template>
                    详情
                  </a-button>
                  <a-popconfirm
                    v-if="bot.admin_enabled"
                    title="确认禁用这个私有 Bot？已提交任务仍会继续完成。"
                    ok-text="禁用"
                    cancel-text="取消"
                    @confirm="setAdminEnabled(bot, false)"
                  >
                    <a-button danger size="small" :loading="actionBotId === bot.id">
                      <template #icon><StopOutlined /></template>
                      禁用
                    </a-button>
                  </a-popconfirm>
                  <a-popconfirm
                    v-else
                    title="确认恢复这个私有 Bot？只有主人未暂停时才会重新接入。"
                    ok-text="恢复"
                    cancel-text="取消"
                    @confirm="setAdminEnabled(bot, true)"
                  >
                    <a-button size="small" type="primary" :loading="actionBotId === bot.id">
                      <template #icon><SafetyCertificateOutlined /></template>
                      恢复
                    </a-button>
                  </a-popconfirm>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <a-empty v-else-if="!loading" description="没有符合条件的私有 Bot" />
    </a-spin>

    <div class="private-bot-admin__pagination">
      <span>{{ rangeText }}</span>
      <a-pagination
        :current="page"
        :page-size="pageSize"
        :total="total"
        :show-size-changer="false"
        show-less-items
        @change="changePage"
      />
    </div>

    <a-modal
      v-model:open="detailOpen"
      title="私有 Bot 详情"
      :width="980"
      :footer="null"
      wrap-class-name="private-bot-admin-detail-modal"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="detail" class="private-bot-detail" data-testid="private-bot-detail">
          <div class="private-bot-detail__summary">
            <div>
              <span>Bot</span>
              <strong>{{ botLabel(detail) }}</strong>
              <small>{{ detail.telegram_display_name || '-' }} · {{ detail.telegram_bot_id }}</small>
            </div>
            <div>
              <span>Owner</span>
              <strong>{{ ownerLabel(detail) }}</strong>
              <small>#{{ detail.owner.id }} · TG {{ detail.owner.telegram_id }}</small>
            </div>
            <div>
              <span>凭据指纹</span>
              <strong>{{ detail.token_fingerprint_hint || '-' }}</strong>
              <small>后台无法读取 token 明文</small>
            </div>
            <div>
              <span>配置版本</span>
              <strong>v{{ detail.config_version }}</strong>
              <small>{{ formatDate(detail.updated_at) }}</small>
            </div>
          </div>

          <a-alert
            v-if="detail.last_error_code || detail.last_error_message"
            type="error"
            show-icon
            :message="detail.last_error_code || '运行异常'"
            :description="detail.last_error_message || '暂无详细错误信息'"
          />

          <div class="private-bot-detail__health">
            <a-tag :color="statusColors[detail.runtime_status]">
              {{ statusLabels[detail.runtime_status] }}
            </a-tag>
            <span>Webhook：{{ formatDate(detail.last_webhook_at) }}</span>
            <span>最近 Update：{{ formatDate(detail.last_update_at) }}</span>
          </div>

          <section>
            <h3>完整配置（只读）</h3>
            <pre data-testid="private-bot-config-readonly">{{ JSON.stringify(detail.config, null, 2) }}</pre>
          </section>

          <section>
            <h3>审计记录</h3>
            <div v-if="detail.audit_logs.length" class="private-bot-detail__audit-list">
              <article v-for="log in detail.audit_logs" :key="log.id">
                <div>
                  <strong>{{ log.action }}</strong>
                  <span>{{ formatDate(log.created_at) }}</span>
                </div>
                <p>
                  {{ log.actor_type }}<template v-if="log.actor_identifier"> · {{ log.actor_identifier }}</template>
                  <template v-if="log.before_status || log.after_status">
                    · {{ log.before_status || '-' }} → {{ log.after_status || '-' }}
                  </template>
                </p>
                <pre v-if="log.details">{{ JSON.stringify(log.details, null, 2) }}</pre>
              </article>
            </div>
            <a-empty v-else description="暂无审计记录" />
          </section>

          <div class="private-bot-detail__danger-zone">
            <div>
              <strong>永久解绑</strong>
              <p>删除 webhook 并失效凭据；用户生成历史不会删除。</p>
            </div>
            <a-popconfirm
              title="这是不可逆操作。确认永久解绑这个私有 Bot？"
              ok-text="永久解绑"
              cancel-text="取消"
              ok-type="danger"
              @confirm="permanentlyUnbind(detail)"
            >
              <a-button danger :loading="actionBotId === detail.id" data-testid="private-bot-delete">
                <template #icon><DeleteOutlined /></template>
                永久解绑
              </a-button>
            </a-popconfirm>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </section>
</template>

<style scoped>
.private-bot-admin {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 18px;
}

.private-bot-admin__hero,
.private-bot-admin__filters,
.private-bot-admin__table-wrap,
.private-bot-admin__pagination {
  border: 1px solid #dbe4ef;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 26px rgba(15, 23, 42, 0.05);
}

.private-bot-admin__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 32%),
    #ffffff;
}

.private-bot-admin__hero h2 {
  margin: 3px 0 5px;
  color: #0f172a;
  font-size: 22px;
}

.private-bot-admin__hero p,
.private-bot-detail__danger-zone p {
  margin: 0;
  color: #64748b;
}

.private-bot-admin__eyebrow {
  color: #2563eb;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.private-bot-admin__filters {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr) 180px 180px auto;
  gap: 12px;
  padding: 16px;
}

.private-bot-admin__filter-actions,
.private-bot-admin__row-actions,
.private-bot-admin__tag-row,
.private-bot-detail__health {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.private-bot-admin__table-wrap {
  overflow-x: auto;
}

.private-bot-admin__table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
  text-align: left;
}

.private-bot-admin__table th,
.private-bot-admin__table td {
  padding: 15px 16px;
  border-bottom: 1px solid #eef2f7;
  vertical-align: top;
}

.private-bot-admin__table th {
  color: #64748b;
  background: #f8fafc;
  font-size: 12px;
  font-weight: 700;
}

.private-bot-admin__table tbody tr:last-child td {
  border-bottom: 0;
}

.private-bot-admin__actions-heading {
  width: 190px;
}

.private-bot-admin__bot-link {
  padding: 0;
  border: 0;
  color: #1d4ed8;
  background: transparent;
  cursor: pointer;
  font-weight: 700;
}

.private-bot-admin__strong {
  color: #1e293b;
  font-weight: 650;
}

.private-bot-admin__muted {
  margin-top: 3px;
  color: #8290a3;
  font-size: 12px;
}

.private-bot-admin__health-message {
  max-width: 260px;
}

.private-bot-admin__error-code {
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
}

.private-bot-admin__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 16px;
  color: #64748b;
  font-size: 13px;
}

.private-bot-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.private-bot-detail__summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.private-bot-detail__summary > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.private-bot-detail__summary span,
.private-bot-detail__summary small {
  overflow: hidden;
  color: #64748b;
  text-overflow: ellipsis;
}

.private-bot-detail h3 {
  margin: 0 0 10px;
  color: #1e293b;
  font-size: 15px;
}

.private-bot-detail section > pre,
.private-bot-detail__audit-list article {
  max-height: 360px;
  margin: 0;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #0f172a;
  color: #dbeafe;
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
}

.private-bot-detail section > pre {
  padding: 16px;
}

.private-bot-detail__audit-list {
  display: grid;
  gap: 10px;
}

.private-bot-detail__audit-list article {
  max-height: none;
  padding: 12px 14px;
  background: #f8fafc;
  color: #334155;
  font-family: inherit;
}

.private-bot-detail__audit-list article > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.private-bot-detail__audit-list p,
.private-bot-detail__audit-list pre {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
}

.private-bot-detail__audit-list pre {
  white-space: pre-wrap;
}

.private-bot-detail__danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff7f7;
}

@media (max-width: 900px) {
  .private-bot-admin__filters,
  .private-bot-detail__summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .private-bot-admin__hero,
  .private-bot-admin__pagination,
  .private-bot-detail__danger-zone {
    align-items: stretch;
    flex-direction: column;
  }

  .private-bot-admin__filters,
  .private-bot-detail__summary {
    grid-template-columns: minmax(0, 1fr);
  }

  .private-bot-admin__filter-actions :deep(.ant-btn) {
    flex: 1;
  }
}
</style>
