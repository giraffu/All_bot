<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { Dayjs } from 'dayjs'
import { Modal, message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

import {
  bulkUpdateAlipayDirectRoster,
  fetchAlipayDirectRoster,
  type AlipayDirectBulkFilters,
  type AlipayDirectRosterFilters,
  type AlipayDirectRosterItem,
} from '../api/alipayDirectRosterApi'

type EnabledFilter = boolean | null
type DirectPaidFilter = boolean | null
type SortField = 'created_at' | 'paid_count' | 'direct_paid_count' | 'id'
type SortOrder = 'asc' | 'desc'

interface TableChangePagination {
  current?: number
  pageSize?: number
}

interface TableSorter {
  field?: SortField
  order?: 'ascend' | 'descend' | null
}

const items = ref<AlipayDirectRosterItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const batchLoading = ref(false)
const selectedRowKeys = ref<number[]>([])
const selectAllMatching = ref(false)
const firstUsedRange = ref<[Dayjs, Dayjs] | null>(null)
const sortBy = ref<SortField>('created_at')
const sortOrder = ref<SortOrder>('desc')

const filters = reactive<{
  minPaidCount: number | null
  maxPaidCount: number | null
  directPaid: DirectPaidFilter
  enabled: EnabledFilter
  query: string
}>({
  minPaidCount: null,
  maxPaidCount: null,
  directPaid: null,
  enabled: true,
  query: '',
})

const columns = [
  { title: '用户', key: 'user', width: 240 },
  {
    title: '首次使用时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 170,
    sorter: true,
  },
  {
    title: '累计付费次数',
    dataIndex: 'paid_count',
    key: 'paid_count',
    width: 140,
    sorter: true,
  },
  {
    title: '直连付款记录',
    dataIndex: 'direct_paid_count',
    key: 'direct_paid_count',
    width: 170,
    sorter: true,
  },
  { title: '当前状态', key: 'status', width: 130 },
  { title: '最近直连付款', key: 'last_direct_paid_at', width: 180 },
]

const dateValue = (value: string | null) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

const currentFilters = (): AlipayDirectRosterFilters => ({
  page: page.value,
  pageSize: pageSize.value,
  minPaidCount: filters.minPaidCount,
  maxPaidCount: filters.maxPaidCount,
  firstUsedFrom: firstUsedRange.value?.[0].format('YYYY-MM-DD') ?? null,
  firstUsedTo: firstUsedRange.value?.[1].format('YYYY-MM-DD') ?? null,
  directPaid: filters.directPaid,
  enabled: filters.enabled,
  query: filters.query.trim() || null,
  sortBy: sortBy.value,
  sortOrder: sortOrder.value,
})

const bulkFilters = (): AlipayDirectBulkFilters => ({
  min_paid_count: filters.minPaidCount,
  max_paid_count: filters.maxPaidCount,
  first_used_from: firstUsedRange.value?.[0].format('YYYY-MM-DD') ?? null,
  first_used_to: firstUsedRange.value?.[1].format('YYYY-MM-DD') ?? null,
  direct_paid: filters.directPaid,
  enabled: filters.enabled,
  query: filters.query.trim() || null,
})

const clearSelection = () => {
  selectedRowKeys.value = []
  selectAllMatching.value = false
}

const loadRoster = async () => {
  loading.value = true
  try {
    const payload = await fetchAlipayDirectRoster(currentFilters())
    items.value = payload.items
    total.value = payload.total
  } catch {
    message.error('支付宝直连名单加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const applyFilters = async () => {
  page.value = 1
  clearSelection()
  await loadRoster()
}

const resetFilters = async () => {
  filters.minPaidCount = null
  filters.maxPaidCount = null
  filters.directPaid = null
  filters.enabled = true
  filters.query = ''
  firstUsedRange.value = null
  sortBy.value = 'created_at'
  sortOrder.value = 'desc'
  await applyFilters()
}

const selectedCount = computed(() =>
  selectAllMatching.value ? total.value : selectedRowKeys.value.length,
)

const rowSelection = computed(() => ({
  selectedRowKeys: selectAllMatching.value
    ? items.value.map(item => item.id)
    : selectedRowKeys.value,
  preserveSelectedRowKeys: true,
  onChange: (keys: Array<string | number>) => {
    selectAllMatching.value = false
    selectedRowKeys.value = keys.map(Number)
  },
}))

const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  pageSizeOptions: ['20', '50', '100'],
  showTotal: (value: number) => `共 ${value} 条`,
}))

const handleTableChange = async (
  nextPagination: TableChangePagination,
  _tableFilters: unknown,
  sorter: TableSorter | TableSorter[],
) => {
  page.value = nextPagination.current ?? 1
  pageSize.value = nextPagination.pageSize ?? pageSize.value
  const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
  if (activeSorter?.field) {
    sortBy.value = activeSorter.field
    sortOrder.value = activeSorter.order === 'ascend' ? 'asc' : 'desc'
  }
  await loadRoster()
}

const executeBatch = async (enabled: boolean) => {
  batchLoading.value = true
  try {
    const result = selectAllMatching.value
      ? await bulkUpdateAlipayDirectRoster({
          enabled,
          selection_mode: 'filters',
          filters: bulkFilters(),
        })
      : await bulkUpdateAlipayDirectRoster({
          enabled,
          selection_mode: 'ids',
          user_ids: selectedRowKeys.value,
        })
    message.success(
      `已匹配 ${result.matched_count} 人，实际更新 ${result.updated_count} 人`,
    )
    clearSelection()
    page.value = 1
    await loadRoster()
  } catch (error: unknown) {
    const detail = (
      error as { response?: { data?: { detail?: string } } }
    )?.response?.data?.detail
    message.error(detail || '批量更新失败，请缩小筛选范围后重试')
  } finally {
    batchLoading.value = false
  }
}

const confirmBatch = (enabled: boolean) => {
  if (selectedCount.value === 0) return
  Modal.confirm({
    title: enabled ? '批量设为支付宝直连用户？' : '批量取消支付宝直连？',
    content: `本次将处理 ${selectedCount.value} 名用户，保存后立即生效。`,
    okText: enabled ? '确认开启' : '确认取消',
    okType: enabled ? 'primary' : 'danger',
    cancelText: '返回',
    onOk: () => executeBatch(enabled),
  })
}

onMounted(loadRoster)
</script>

<template>
  <div class="alipay-direct-roster flex min-h-0 flex-1 flex-col gap-4">
    <a-card :bordered="false" class="roster-filter-card shrink-0">
      <div class="filter-grid">
        <div class="filter-field">
          <span class="filter-label">当前直连状态</span>
          <a-select v-model:value="filters.enabled" class="w-full">
            <a-select-option :value="true">已开启直连</a-select-option>
            <a-select-option :value="false">未开启直连</a-select-option>
            <a-select-option :value="null">全部用户</a-select-option>
          </a-select>
        </div>

        <div class="filter-field paid-count-filter">
          <span class="filter-label">累计付费次数</span>
          <div class="flex items-center gap-2">
            <a-input-number
              v-model:value="filters.minPaidCount"
              :min="0"
              placeholder="最少"
              class="min-w-0 flex-1"
            />
            <span class="text-gray-400">—</span>
            <a-input-number
              v-model:value="filters.maxPaidCount"
              :min="0"
              placeholder="最多"
              class="min-w-0 flex-1"
            />
          </div>
        </div>

        <div class="filter-field">
          <span class="filter-label">首次使用时间</span>
          <a-range-picker
            v-model:value="firstUsedRange"
            class="w-full"
            format="YYYY-MM-DD"
          />
        </div>

        <div class="filter-field">
          <span class="filter-label">是否直连付款过</span>
          <a-select v-model:value="filters.directPaid" class="w-full">
            <a-select-option :value="null">全部</a-select-option>
            <a-select-option :value="true">是</a-select-option>
            <a-select-option :value="false">否</a-select-option>
          </a-select>
        </div>

        <div class="filter-field roster-search-field">
          <span class="filter-label">用户搜索</span>
          <a-input-search
            v-model:value="filters.query"
            placeholder="内部 ID、用户名或昵称"
            allow-clear
            @search="applyFilters"
          />
        </div>

        <div class="filter-actions">
          <a-button type="primary" @click="applyFilters">
            <template #icon><SearchOutlined /></template>
            筛选
          </a-button>
          <a-button @click="resetFilters">
            <template #icon><ReloadOutlined /></template>
            重置
          </a-button>
        </div>
      </div>
    </a-card>

    <a-alert
      message="保存后立即影响该用户下一笔支付宝订单；微信仍使用原支付渠道。"
      type="info"
      show-icon
      class="shrink-0"
    />

    <div class="roster-table-panel flex min-h-0 flex-1 flex-col rounded-xl border bg-white">
      <div class="batch-toolbar">
        <div class="batch-summary">
          <strong>匹配 {{ total }} 人</strong>
          <span class="text-gray-400">·</span>
          <span>已选择 {{ selectedCount }} 人</span>
          <a-checkbox
            v-model:checked="selectAllMatching"
            class="select-all-matching"
            :disabled="total === 0"
            @change="selectedRowKeys = []"
          >
            选择全部筛选结果（跨分页）
          </a-checkbox>
        </div>
        <div class="batch-buttons">
          <a-button
            type="primary"
            :loading="batchLoading"
            :disabled="selectedCount === 0"
            @click="confirmBatch(true)"
          >
            <template #icon><CheckCircleOutlined /></template>
            批量设为直连
          </a-button>
          <a-button
            danger
            :loading="batchLoading"
            :disabled="selectedCount === 0"
            @click="confirmBatch(false)"
          >
            <template #icon><CloseCircleOutlined /></template>
            批量取消直连
          </a-button>
        </div>
      </div>

      <a-table
        row-key="id"
        class="roster-table min-h-0 flex-1"
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :pagination="pagination"
        :row-selection="rowSelection"
        :scroll="{ x: 1060, y: 'calc(100vh - 500px)' }"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'user'">
            <div class="user-cell">
              <strong>{{ record.full_name || record.username || `用户 ${record.id}` }}</strong>
              <span v-if="record.username" class="user-handle">@{{ record.username }}</span>
              <span class="user-id">ID {{ record.id }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ dateValue(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'paid_count'">
            <a-tag color="blue">{{ record.paid_count }} 次</a-tag>
          </template>
          <template v-else-if="column.key === 'direct_paid_count'">
            <a-tag :color="record.has_direct_paid ? 'green' : 'default'">
              {{ record.has_direct_paid ? `${record.direct_paid_count} 次` : '未付过' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.alipay_direct_enabled ? 'processing' : 'default'">
              {{ record.alipay_direct_enabled ? '已开启' : '未开启' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'last_direct_paid_at'">
            {{ dateValue(record.last_direct_paid_at) }}
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<style scoped>
.filter-grid {
  display: grid;
  grid-template-columns: 160px minmax(210px, 0.9fr) minmax(260px, 1fr) 180px minmax(220px, 1fr) auto;
  gap: 14px;
  align-items: end;
}

.filter-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 7px;
}

.filter-label {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.filter-actions,
.batch-buttons,
.batch-summary {
  display: flex;
  align-items: center;
  gap: 10px;
}

.roster-table-panel {
  overflow: hidden;
}

.batch-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-handle {
  color: #1677ff;
  font-size: 12px;
}

.user-id {
  color: #94a3b8;
  font-size: 12px;
}

:deep(.ant-table-wrapper),
:deep(.ant-spin-nested-loading),
:deep(.ant-spin-container) {
  min-height: 0;
}

@media (max-width: 1700px) {
  .filter-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }

  .filter-actions,
  .batch-buttons,
  .batch-summary {
    flex-wrap: wrap;
  }

  .batch-toolbar {
    align-items: stretch;
  }
}
</style>
