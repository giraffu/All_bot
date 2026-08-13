<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'

import {
  fetchPaidGroupGuardConfig,
  fetchPaidGroupGuardLogs,
  fetchGroupManageConfig,
  fetchGroupManageLogs,
  updatePaidGroupGuardConfig,
  updateGroupManageConfig,
} from '../api/api'

const props = withDefaults(defineProps<{ mode?: 'paid-guard' | 'group-manage' }>(), {
  mode: 'paid-guard',
})
const isGroupManage = computed(() => props.mode === 'group-manage')
const panelTitle = computed(() => isGroupManage.value ? '群管理 Bot' : '群审核 Bot')

interface PaidGroupGuardConfig {
  enabled: boolean
  dry_run: boolean
  block_links: boolean
  allowed_domains: string[]
  forbidden_words: string[]
  exempt_user_ids: number[]
  config_path?: string
  log_path?: string
}

interface PaidGroupGuardLogItem {
  timestamp: string
  chat_id: number
  message_id: number
  user_id: number
  username?: string | null
  full_name?: string | null
  reason: string
  matched_value?: string | null
  text_snippet: string
  action: string
  error?: string | null
}

const defaultConfig = (): PaidGroupGuardConfig => ({
  enabled: true,
  dry_run: false,
  block_links: true,
  allowed_domains: [],
  forbidden_words: [],
  exempt_user_ids: [],
})

const loadingConfig = ref(false)
const savingConfig = ref(false)
const loadingLogs = ref(false)
const config = reactive<PaidGroupGuardConfig>(defaultConfig())
const allowedDomainsText = ref('')
const forbiddenWordsText = ref('')
const exemptUserIdsText = ref('')
const logs = ref<PaidGroupGuardLogItem[]>([])
const totalLogs = ref(0)
const logPagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50', '100'],
})
const logFilters = reactive({
  reason: undefined as string | undefined,
  userId: '',
  dateRange: [] as unknown[],
})

const configStatus = computed(() => {
  if (!config.enabled) return '关闭'
  return config.dry_run ? '观察' : '真实删除'
})

const columns = [
  { title: '时间', dataIndex: 'timestamp', width: 180 },
  { title: '用户', dataIndex: 'user', width: 180 },
  { title: '原因', dataIndex: 'reason', width: 120 },
  { title: '动作', dataIndex: 'action', width: 120 },
  { title: '命中', dataIndex: 'matched_value', width: 220, ellipsis: true },
  { title: '消息片段', dataIndex: 'text_snippet', ellipsis: true },
  { title: '错误', dataIndex: 'error', width: 220, ellipsis: true },
]

const reasonOptions = [
  { label: '链接', value: 'link' },
  { label: '违禁词', value: 'forbidden_word' },
]

const splitList = (value: string): string[] =>
  value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean)

const splitUserIds = (value: string): number[] => {
  const seen = new Set<number>()
  const ids: number[] = []
  splitList(value).forEach((item) => {
    const id = Number.parseInt(item, 10)
    if (Number.isFinite(id) && id > 0 && !seen.has(id)) {
      seen.add(id)
      ids.push(id)
    }
  })
  return ids
}

const joinList = (items: Array<string | number>): string => items.join('\n')

const applyConfig = (payload: Partial<PaidGroupGuardConfig>) => {
  Object.assign(config, defaultConfig(), payload)
  allowedDomainsText.value = joinList(config.allowed_domains)
  forbiddenWordsText.value = joinList(config.forbidden_words)
  exemptUserIdsText.value = joinList(config.exempt_user_ids)
}

const loadConfig = async () => {
  loadingConfig.value = true
  try {
    const payload = await (isGroupManage.value ? fetchGroupManageConfig() : fetchPaidGroupGuardConfig())
    applyConfig(payload)
  } catch {
    message.error(`加载${panelTitle.value}配置失败`)
  } finally {
    loadingConfig.value = false
  }
}

const saveConfig = async () => {
  savingConfig.value = true
  try {
    const payload = {
      enabled: config.enabled,
      dry_run: config.dry_run,
      block_links: config.block_links,
      allowed_domains: splitList(allowedDomainsText.value),
      forbidden_words: splitList(forbiddenWordsText.value),
      exempt_user_ids: splitUserIds(exemptUserIdsText.value),
    }
    const saved = await (isGroupManage.value ? updateGroupManageConfig(payload) : updatePaidGroupGuardConfig(payload))
    applyConfig(saved)
    message.success(`${panelTitle.value}配置已保存`)
  } catch {
    message.error(`保存${panelTitle.value}配置失败`)
  } finally {
    savingConfig.value = false
  }
}

const loadLogs = async () => {
  loadingLogs.value = true
  try {
    const fetchLogs = isGroupManage.value ? fetchGroupManageLogs : fetchPaidGroupGuardLogs
    const payload = await fetchLogs({
      page: logPagination.current,
      pageSize: logPagination.pageSize,
      reason: logFilters.reason || null,
      userId: logFilters.userId || null,
      startDate: logFilters.dateRange?.[0]
        ? dayjs(logFilters.dateRange[0] as string).format('YYYY-MM-DD')
        : null,
      endDate: logFilters.dateRange?.[1]
        ? dayjs(logFilters.dateRange[1] as string).format('YYYY-MM-DD')
        : null,
    })
    logs.value = payload.items ?? []
    totalLogs.value = payload.total ?? 0
  } catch {
    message.error(`加载${panelTitle.value}日志失败`)
  } finally {
    loadingLogs.value = false
  }
}

const handleLogTableChange = (pagination: { current: number; pageSize: number }) => {
  logPagination.current = pagination.current
  logPagination.pageSize = pagination.pageSize
  void loadLogs()
}

const searchLogs = () => {
  logPagination.current = 1
  void loadLogs()
}

const resetLogFilters = () => {
  logFilters.reason = undefined
  logFilters.userId = ''
  logFilters.dateRange = []
  searchLogs()
}

const formatTime = (value: string) => {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

const formatUser = (record: PaidGroupGuardLogItem) => {
  const name = record.username ? `@${record.username}` : record.full_name || '-'
  return `${name} (${record.user_id})`
}

onMounted(() => {
  void loadConfig()
  void loadLogs()
})
</script>

<template>
  <div class="paid-group-guard flex-1 flex flex-col gap-5">
    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold text-slate-900">{{ panelTitle }}</h2>
          <div class="mt-1 text-sm text-slate-500">状态：{{ configStatus }}</div>
        </div>
        <div class="flex items-center gap-2">
          <a-button :loading="loadingConfig" @click="loadConfig">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" :loading="savingConfig" @click="saveConfig">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
        </div>
      </div>

      <a-spin :spinning="loadingConfig">
        <div class="grid gap-5 lg:grid-cols-[280px_1fr]">
          <div class="rounded-lg border border-slate-200 p-4">
            <div class="space-y-4">
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm font-medium text-slate-700">启用</span>
                <a-switch v-model:checked="config.enabled" />
              </div>
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm font-medium text-slate-700">观察模式</span>
                <a-switch v-model:checked="config.dry_run" />
              </div>
              <div class="flex items-center justify-between gap-3">
                <span class="text-sm font-medium text-slate-700">删除链接</span>
                <a-switch v-model:checked="config.block_links" />
              </div>
            </div>
          </div>

          <div class="grid gap-4 lg:grid-cols-3">
            <a-form-item label="允许域名">
              <a-textarea
                v-model:value="allowedDomainsText"
                :rows="8"
                placeholder="aivison.it.com"
              />
            </a-form-item>
            <a-form-item label="违禁词">
              <a-textarea
                v-model:value="forbiddenWordsText"
                :rows="8"
                placeholder="spam"
              />
            </a-form-item>
            <a-form-item label="豁免用户 ID">
              <a-textarea
                v-model:value="exemptUserIdsText"
                :rows="8"
                placeholder="123456789"
              />
            </a-form-item>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="min-h-0 flex-1 rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-base font-semibold text-slate-900">删除日志</h3>
        <a-button :loading="loadingLogs" @click="loadLogs">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>

      <div class="mb-4 flex flex-wrap items-center gap-3">
        <a-select
          v-model:value="logFilters.reason"
          allow-clear
          placeholder="原因"
          class="w-36"
          :options="reasonOptions"
        />
        <a-input
          v-model:value="logFilters.userId"
          allow-clear
          placeholder="用户 ID"
          class="w-40"
        />
        <a-range-picker v-model:value="logFilters.dateRange" />
        <a-button type="primary" @click="searchLogs">查询</a-button>
        <a-button @click="resetLogFilters">重置</a-button>
      </div>

      <a-table
        row-key="message_id"
        size="small"
        :loading="loadingLogs"
        :columns="columns"
        :data-source="logs"
        :pagination="{ ...logPagination, total: totalLogs }"
        :scroll="{ x: 1180 }"
        @change="handleLogTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'timestamp'">
            {{ formatTime(record.timestamp) }}
          </template>
          <template v-else-if="column.dataIndex === 'user'">
            {{ formatUser(record) }}
          </template>
          <template v-else-if="column.dataIndex === 'reason'">
            <a-tag :color="record.reason === 'link' ? 'blue' : 'red'">
              {{ record.reason === 'link' ? '链接' : '违禁词' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'action'">
            <a-tag :color="record.action === 'deleted' ? 'green' : record.action === 'dry_run' ? 'gold' : 'volcano'">
              {{ record.action }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'matched_value'">
            <span class="break-all">{{ record.matched_value || '-' }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'text_snippet'">
            <span class="break-all">{{ record.text_snippet || '-' }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'error'">
            <span class="break-all text-red-600">{{ record.error || '-' }}</span>
          </template>
        </template>
      </a-table>
    </section>
  </div>
</template>
