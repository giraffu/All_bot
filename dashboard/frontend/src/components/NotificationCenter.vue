<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  fetchNotificationCenterSettings,
  fetchObserverNotificationLogs,
  fetchObserverReports,
  updateNotificationCenterSettings,
  type NotificationCenterSettings,
  type ObserverNotificationRecord,
  type ObserverReportRecord,
} from '../api/notificationCenterApi'

type ViewKey = 'settings' | 'reports' | 'notifications'

const activeView = ref<ViewKey>('settings')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const adminIdsText = ref('')
const groupIdsText = ref('')
const supportIdsText = ref('')
const queueThresholds = reactive({
  queue_total_pending_threshold: 20,
  queue_type_pending_threshold: 10,
})
const flags = reactive({
  queue_alerts_enabled: true,
  group_collection_enabled: true,
  daily_reports_enabled: false,
  weekly_reports_enabled: false,
  monthly_reports_enabled: false,
})
const reports = ref<ObserverReportRecord[]>([])
const notifications = ref<ObserverNotificationRecord[]>([])
const selectedReport = ref<ObserverReportRecord | null>(null)
const reportTotal = ref(0)
const notificationTotal = ref(0)
const reportPage = ref(1)
const notificationPage = ref(1)
const pageSize = 20

const tabs: Array<{ key: ViewKey; label: string }> = [
  { key: 'settings', label: '通知设置' },
  { key: 'reports', label: '报告记录' },
  { key: 'notifications', label: '通知记录' },
]

const reportHasNext = computed(() => reportPage.value * pageSize < reportTotal.value)
const notificationHasNext = computed(
  () => notificationPage.value * pageSize < notificationTotal.value,
)

const applySettings = (settings: NotificationCenterSettings) => {
  adminIdsText.value = settings.admin_telegram_user_ids.join('\n')
  groupIdsText.value = settings.authorized_group_ids.join('\n')
  supportIdsText.value = settings.support_ticket_user_ids.join('\n')
  flags.queue_alerts_enabled = settings.queue_alerts_enabled
  queueThresholds.queue_total_pending_threshold = settings.queue_total_pending_threshold
  queueThresholds.queue_type_pending_threshold = settings.queue_type_pending_threshold
  flags.group_collection_enabled = settings.group_collection_enabled
  flags.daily_reports_enabled = settings.daily_reports_enabled
  flags.weekly_reports_enabled = settings.weekly_reports_enabled
  flags.monthly_reports_enabled = settings.monthly_reports_enabled
}

const parseIds = (value: string, kind: 'user' | 'group'): number[] => {
  const tokens = value.split(/[\s,，]+/).filter(Boolean)
  if (tokens.some(token => !/^-?\d+$/.test(token))) throw new Error('ID 必须是整数')
  const ids = [...new Set(tokens.map(Number))]
  if (ids.some(id => !Number.isSafeInteger(id) || (kind === 'user' ? id <= 0 : id === 0))) {
    throw new Error(kind === 'user' ? '用户 ID 必须是正整数' : '群 ID 不能为 0')
  }
  return ids
}

const loadSettings = async () => {
  loading.value = true
  error.value = ''
  try {
    applySettings(await fetchNotificationCenterSettings())
  } catch {
    error.value = '通知设置加载失败，请检查 observer 数据库连接。'
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  error.value = ''
  saved.value = false
  let payload: NotificationCenterSettings
  try {
    if (
      !Number.isInteger(queueThresholds.queue_total_pending_threshold)
      || queueThresholds.queue_total_pending_threshold < 1
      || queueThresholds.queue_total_pending_threshold > 100_000
      || !Number.isInteger(queueThresholds.queue_type_pending_threshold)
      || queueThresholds.queue_type_pending_threshold < 1
      || queueThresholds.queue_type_pending_threshold > 100_000
    ) {
      throw new Error('排队阈值必须是 1 到 100000 的整数')
    }
    payload = {
      admin_telegram_user_ids: parseIds(adminIdsText.value, 'user'),
      authorized_group_ids: parseIds(groupIdsText.value, 'group'),
      support_ticket_user_ids: parseIds(supportIdsText.value, 'user'),
      ...queueThresholds,
      ...flags,
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'ID 格式不正确'
    return
  }
  saving.value = true
  try {
    applySettings(await updateNotificationCenterSettings(payload))
    saved.value = true
  } catch {
    error.value = '保存失败，现有设置未被页面覆盖。'
  } finally {
    saving.value = false
  }
}

const loadReports = async () => {
  loading.value = true
  error.value = ''
  try {
    const result = await fetchObserverReports(reportPage.value, pageSize)
    reports.value = result.items
    reportTotal.value = result.total
  } catch {
    error.value = '报告记录加载失败。'
  } finally {
    loading.value = false
  }
}

const loadNotifications = async () => {
  loading.value = true
  error.value = ''
  try {
    const result = await fetchObserverNotificationLogs(notificationPage.value, pageSize)
    notifications.value = result.items
    notificationTotal.value = result.total
  } catch {
    error.value = '通知记录加载失败。'
  } finally {
    loading.value = false
  }
}

const selectView = async (view: ViewKey) => {
  activeView.value = view
  if (view === 'settings') await loadSettings()
  if (view === 'reports') await loadReports()
  if (view === 'notifications') await loadNotifications()
}

const changeReportPage = async (delta: number) => {
  reportPage.value += delta
  await loadReports()
}

const changeNotificationPage = async (delta: number) => {
  notificationPage.value += delta
  await loadNotifications()
}

onMounted(loadSettings)
</script>

<template>
  <main class="notification-center">
    <header class="page-header">
      <div>
        <p class="eyebrow">OBSERVER BOT</p>
        <h1>通知中心</h1>
        <p>集中管理工单通知、队列告警、授权群采集和本地模型报告。</p>
      </div>
      <span class="isolation-badge">独立 observer_prod</span>
    </header>

    <nav class="view-tabs" aria-label="通知中心页面">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="{ active: activeView === tab.key }"
        type="button"
        @click="selectView(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <p v-if="error" class="feedback error">{{ error }}</p>
    <p v-if="saved" class="feedback success">设置已保存，observer-bot 最多约 15 秒后生效。</p>

    <section v-if="activeView === 'settings'" class="settings-layout" :aria-busy="loading">
      <article class="card recipients-card">
        <div class="card-heading"><div><h2>Telegram 接收与采集</h2><p>每行一个数字 ID，也支持逗号分隔。</p></div></div>
        <label>
          Observer 管理员用户 ID
          <textarea data-testid="observer-admin-ids" v-model="adminIdsText" rows="5" placeholder="123456789" />
          <small>管理员需要先私聊并启动 @qq_notification_bot。</small>
        </label>
        <label>
          授权群 ID
          <textarea data-testid="authorized-group-ids" v-model="groupIdsText" rows="5" placeholder="-1001234567890" />
          <small>Bot 必须已加入群；只采集文字与图片说明文字，不下载媒体。</small>
        </label>
        <label>
          客服工单通知用户 ID
          <textarea v-model="supportIdsText" rows="4" placeholder="123456789" />
          <small>由现有客服 Bot 发送，不经过 observer-bot。</small>
        </label>
      </article>

      <article class="card switches-card">
        <div class="card-heading"><div><h2>功能开关</h2><p>各功能相互独立，关闭报告不会影响队列告警。</p></div></div>
        <div class="switch-row"><div><b>AllBot 队列告警</b><span>仅按总排队或单类型排队数量告警</span></div><a-switch v-model:checked="flags.queue_alerts_enabled" /></div>
        <div class="threshold-panel">
          <div class="threshold-heading"><b>拥堵阈值</b><span>超过任一数量设置值时通知管理员，保存后约 15 秒生效。</span></div>
          <div class="threshold-grid">
            <label>
              总排队数量
              <input data-testid="queue-total-threshold" v-model.number="queueThresholds.queue_total_pending_threshold" type="number" min="1" max="100000" step="1" />
              <small>所有任务类型的待处理数量合计。</small>
            </label>
            <label>
              单个类型排队数量
              <input data-testid="queue-type-threshold" v-model.number="queueThresholds.queue_type_pending_threshold" type="number" min="1" max="100000" step="1" />
              <small>任一任务类型超过此数量即告警。</small>
            </label>
          </div>
        </div>
        <div class="switch-row"><div><b>授权群消息采集</b><span>日报、周报、月报的数据来源</span></div><a-switch v-model:checked="flags.group_collection_enabled" /></div>
        <div class="switch-row"><div><b>日报</b><span>每天按设定时区生成</span></div><a-switch v-model:checked="flags.daily_reports_enabled" /></div>
        <div class="switch-row"><div><b>周报</b><span>每周汇总授权群信息</span></div><a-switch v-model:checked="flags.weekly_reports_enabled" /></div>
        <div class="switch-row"><div><b>月报</b><span>每月汇总授权群信息</span></div><a-switch v-model:checked="flags.monthly_reports_enabled" /></div>
        <div class="lm-note"><b>LM Studio</b><p>只在生成报告时调用。本地服务不可用时，工单通知与队列告警仍继续运行。</p></div>
        <button data-testid="save-settings" class="primary-button" type="button" :disabled="saving || loading" @click="saveSettings">
          {{ saving ? '保存中…' : '保存全部设置' }}
        </button>
      </article>
    </section>

    <section v-else-if="activeView === 'reports'" class="card records-card" :aria-busy="loading">
      <div class="card-heading"><div><h2>报告记录</h2><p>保留生成状态、使用模型和报告正文。</p></div><button type="button" @click="loadReports">刷新</button></div>
      <div class="table-scroll"><table><thead><tr><th>周期</th><th>状态</th><th>模型</th><th>更新时间</th><th></th></tr></thead><tbody><tr v-for="report in reports" :key="report.run_key"><td><b>{{ report.report_type }}</b><small>{{ report.period_start }} → {{ report.period_end }}</small></td><td><span :class="`status ${report.status}`">{{ report.status }}</span></td><td>{{ report.model_id || '—' }}</td><td>{{ report.updated_at }}</td><td><button type="button" @click="selectedReport = report">查看</button></td></tr><tr v-if="!reports.length"><td colspan="5" class="empty">还没有报告记录</td></tr></tbody></table></div>
      <div class="pager"><button :disabled="reportPage === 1" @click="changeReportPage(-1)">上一页</button><span>第 {{ reportPage }} 页 · 共 {{ reportTotal }} 条</span><button :disabled="!reportHasNext" @click="changeReportPage(1)">下一页</button></div>
      <article v-if="selectedReport" class="report-detail"><button class="close-detail" @click="selectedReport = null">关闭</button><h3>{{ selectedReport.run_key }}</h3><pre>{{ selectedReport.content || selectedReport.error || '暂无正文' }}</pre></article>
    </section>

    <section v-else class="card records-card" :aria-busy="loading">
      <div class="card-heading"><div><h2>通知记录</h2><p>记录 observer-bot 的发送结果；正文只保留有限预览。</p></div><button type="button" @click="loadNotifications">刷新</button></div>
      <div class="table-scroll"><table><thead><tr><th>类型</th><th>接收者</th><th>结果</th><th>内容预览</th><th>时间</th></tr></thead><tbody><tr v-for="item in notifications" :key="item.id"><td>{{ item.event_type }}</td><td>{{ item.destination_chat_id || '—' }}</td><td><span :class="`status ${item.status}`">{{ item.status }}</span></td><td class="preview">{{ item.content_preview }}</td><td>{{ item.created_at }}</td></tr><tr v-if="!notifications.length"><td colspan="5" class="empty">还没有通知记录</td></tr></tbody></table></div>
      <div class="pager"><button :disabled="notificationPage === 1" @click="changeNotificationPage(-1)">上一页</button><span>第 {{ notificationPage }} 页 · 共 {{ notificationTotal }} 条</span><button :disabled="!notificationHasNext" @click="changeNotificationPage(1)">下一页</button></div>
    </section>
  </main>
</template>

<style scoped>
.notification-center{--ink:#13213c;--muted:#64748b;display:flex;flex-direction:column;gap:18px;min-height:100%;color:var(--ink)}
.page-header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:4px 2px}.page-header h1{font-size:28px;margin:2px 0 6px}.page-header p{margin:0;color:var(--muted)}.eyebrow{font-size:11px!important;font-weight:700;letter-spacing:.18em;color:#1677ff!important}.isolation-badge{white-space:nowrap;padding:8px 12px;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;border-radius:999px;font-size:12px;font-weight:600}
.view-tabs{display:flex;gap:6px;padding:5px;background:#eef2f7;border-radius:12px;width:max-content}.view-tabs button{border:0;background:transparent;padding:8px 15px;border-radius:8px;color:#475569;cursor:pointer}.view-tabs button.active{background:#fff;color:#1677ff;box-shadow:0 1px 4px #0f172a1a;font-weight:600}
.settings-layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);gap:18px}.card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 5px 18px #0f172a0a}.card-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:15px;margin-bottom:18px}.card-heading h2{font-size:17px;margin:0 0 4px}.card-heading p{margin:0;color:var(--muted);font-size:13px}.card-heading button,.records-card button,.pager button{border:1px solid #cbd5e1;background:#fff;border-radius:7px;padding:6px 11px;cursor:pointer}
label{display:block;font-weight:600;margin-top:15px}textarea{display:block;width:100%;box-sizing:border-box;margin:7px 0 5px;border:1px solid #cbd5e1;border-radius:9px;padding:10px 12px;resize:vertical;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}textarea:focus{outline:2px solid #bfdbfe;border-color:#60a5fa}small{display:block;color:var(--muted);font-weight:400}
.switch-row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 0;border-bottom:1px solid #edf2f7}.switch-row b,.switch-row span{display:block}.switch-row span{font-size:12px;color:var(--muted);margin-top:3px}.lm-note{margin:18px 0;padding:13px;background:#f8fafc;border-left:3px solid #60a5fa;border-radius:7px}.lm-note p{margin:4px 0 0;color:var(--muted);font-size:12px}.primary-button{width:100%;border:0;border-radius:9px;padding:11px;background:#1677ff;color:#fff;font-weight:600;cursor:pointer}.primary-button:disabled{opacity:.55}.feedback{margin:0;padding:10px 13px;border-radius:8px}.feedback.error{background:#fff1f0;color:#b42318}.feedback.success{background:#f0fdf4;color:#15803d}
.threshold-panel{padding:14px 0 16px;border-bottom:1px solid #edf2f7}.threshold-heading b,.threshold-heading span{display:block}.threshold-heading span{margin-top:3px;color:var(--muted);font-size:12px}.threshold-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.threshold-grid label{margin-top:12px;font-size:13px}.threshold-grid input{display:block;width:100%;box-sizing:border-box;margin:7px 0 5px;border:1px solid #cbd5e1;border-radius:9px;padding:9px 10px;color:var(--ink);font:600 14px/1.4 inherit}.threshold-grid input:focus{outline:2px solid #bfdbfe;border-color:#60a5fa}
.records-card{position:relative;min-height:400px}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #edf2f7;vertical-align:top}th{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.06em}.status{display:inline-block;padding:3px 8px;border-radius:999px;background:#f1f5f9}.status.completed,.status.sent{background:#dcfce7;color:#166534}.status.failed{background:#fee2e2;color:#991b1b}.status.running{background:#dbeafe;color:#1e40af}.preview{max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.empty{text-align:center;color:var(--muted);padding:48px}.pager{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px;color:var(--muted);font-size:12px}.pager button:disabled{opacity:.4}.report-detail{position:absolute;inset:72px 20px 20px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:18px;box-shadow:0 12px 36px #0f172a1f;overflow:auto}.report-detail h3{margin-top:0}.report-detail pre{white-space:pre-wrap;font:13px/1.7 inherit}.close-detail{float:right}
@media(max-width:900px){.settings-layout{grid-template-columns:1fr}.page-header{flex-direction:column}.isolation-badge{align-self:flex-start}.view-tabs{width:100%;box-sizing:border-box}.view-tabs button{flex:1}.card{padding:16px}}
@media(max-width:520px){.threshold-grid{grid-template-columns:1fr}}
</style>
