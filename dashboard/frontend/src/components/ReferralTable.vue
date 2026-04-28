<script setup>
import { ref, onMounted, computed } from 'vue'
import { fetchReferralRewards } from '../api/api'
import { message } from 'ant-design-vue'

const loading = ref(false)
const data = ref([])

const loadData = async () => {
  loading.value = true
  try {
    const res = await fetchReferralRewards()
    data.value = res
  } catch (error) {
    console.error(error)
    message.error('获取邀请奖励数据失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})

const summaryStats = computed(() => {
  let rewardedInvitersCount = 0
  let totalCommission = 0
  let totalInvitations = 0
  let totalRMB = 0
  let totalTON = 0
  let totalStars = 0

  data.value.forEach(item => {
    if (item.commission_usdt > 0) {
      rewardedInvitersCount += 1
    }
    totalCommission += (item.commission_usdt || 0)
    totalInvitations += (item.total_invitations || 0)
    totalRMB += (item.total_rmb || 0)
    totalTON += (item.total_ton || 0)
    totalStars += (item.total_stars || 0)
  })

  return {
    rewardedInvitersCount,
    totalCommission: totalCommission.toFixed(2),
    totalInvitations,
    totalRMB: totalRMB.toFixed(2),
    totalTON: totalTON.toFixed(2),
    totalStars
  }
})

const columns = [
  {
    title: '邀请人名称',
    dataIndex: 'inviter_name',
    key: 'inviter_name',
    width: '12%'
  },
  {
    title: '邀请人 ID (TG)',
    dataIndex: 'inviter_telegram_id',
    key: 'inviter_telegram_id',
    width: '12%'
  },
  {
    title: '总邀请人数',
    dataIndex: 'total_invitations',
    key: 'total_invitations',
    width: '10%',
    sorter: (a, b) => a.total_invitations - b.total_invitations
  },
  {
    title: '充值转化人数',
    dataIndex: 'total_invitees',
    key: 'total_invitees',
    width: '10%',
    sorter: (a, b) => a.total_invitees - b.total_invitees
  },
  {
    title: '充值转化率',
    dataIndex: 'conversion_rate',
    key: 'conversion_rate',
    width: '10%',
    sorter: (a, b) => a.conversion_rate - b.conversion_rate
  },
  {
    title: '受邀者充值(Stars)',
    dataIndex: 'total_stars',
    key: 'total_stars',
    width: '10%'
  },
  {
    title: '受邀者充值(TON)',
    dataIndex: 'total_ton',
    key: 'total_ton',
    width: '10%'
  },
  {
    title: '受邀者充值(RMB)',
    dataIndex: 'total_rmb',
    key: 'total_rmb',
    width: '10%'
  },
  {
    title: '总计折合(USDT)',
    dataIndex: 'total_usdt',
    key: 'total_usdt',
    width: '10%',
    sorter: (a, b) => a.total_usdt - b.total_usdt
  },
  {
    title: '分成金额(USDT)',
    dataIndex: 'commission_usdt',
    key: 'commission_usdt',
    width: '10%',
    sorter: (a, b) => a.commission_usdt - b.commission_usdt
  }
]

const innerColumns = [
  {
    title: '受邀者名称',
    dataIndex: 'invitee_name',
    key: 'invitee_name'
  },
  {
    title: '受邀者 ID',
    dataIndex: 'invitee_telegram_id',
    key: 'invitee_telegram_id'
  },
  {
    title: '充值笔数',
    dataIndex: 'recharge_count',
    key: 'recharge_count'
  },
  {
    title: '分成金额(USDT)',
    dataIndex: 'commission_usdt',
    key: 'commission_usdt'
  }
]

const orderColumns = [
  {
    title: '订单类型',
    dataIndex: 'type',
    key: 'type'
  },
  {
    title: '充值金额',
    dataIndex: 'amount',
    key: 'amount'
  },
  {
    title: '时间',
    dataIndex: 'date',
    key: 'date'
  },
  {
    title: '系统订单号',
    dataIndex: 'order_id',
    key: 'order_id'
  }
]

</script>

<template>
  <div class="h-full flex flex-col">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-xl font-bold text-gray-800 m-0">邀请奖励与充值数据分析</h2>
      <a-button type="primary" @click="loadData" :loading="loading">
        刷新数据
      </a-button>
    </div>

    <a-row :gutter="16" class="mb-4">
      <a-col :span="12">
        <a-card class="shadow-sm border border-gray-100 h-full">
          <div class="flex justify-around items-center">
            <a-statistic title="获奖邀请人数" :value="summaryStats.rewardedInvitersCount" />
            <a-statistic title="总分成金额 (USDT)" :value="summaryStats.totalCommission" prefix="$" />
            <a-statistic title="总邀请人数" :value="summaryStats.totalInvitations" />
          </div>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card class="shadow-sm border border-gray-100 h-full">
          <div class="flex justify-around items-center">
            <a-statistic title="受邀者总充值 (RMB)" :value="summaryStats.totalRMB" prefix="¥" />
            <a-statistic title="受邀者总充值 (TON)" :value="summaryStats.totalTON" suffix="TON" />
            <a-statistic title="受邀者总充值 (Stars)" :value="summaryStats.totalStars" suffix="⭐" />
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-table
      :columns="columns"
      :data-source="data"
      row-key="inviter_telegram_id"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      class="flex-1 bg-white rounded-lg shadow-sm overflow-hidden border border-gray-100"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'total_stars'">
          <span class="font-bold text-amber-500">{{ record.total_stars }} ⭐</span>
        </template>
        <template v-else-if="column.key === 'total_ton'">
          <span class="font-bold text-blue-500">{{ record.total_ton }} TON</span>
        </template>
        <template v-else-if="column.key === 'total_rmb'">
          <span class="font-bold text-red-500">¥ {{ record.total_rmb }}</span>
        </template>
        <template v-else-if="column.key === 'total_usdt'">
          <span class="font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded border border-emerald-100">$ {{ record.total_usdt }}</span>
        </template>
        <template v-else-if="column.key === 'commission_usdt'">
          <span class="font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded border border-indigo-100">$ {{ record.commission_usdt }}</span>
        </template>
        <template v-else-if="column.key === 'total_invitations'">
          <a-tag color="purple">{{ record.total_invitations }}</a-tag>
        </template>
        <template v-else-if="column.key === 'total_invitees'">
          <a-tag color="green">{{ record.total_invitees }}</a-tag>
        </template>
        <template v-else-if="column.key === 'conversion_rate'">
          <span class="font-medium text-slate-600">{{ record.conversion_rate }}%</span>
        </template>
      </template>

      <template #expandedRowRender="{ record }">
        <a-table
          :columns="innerColumns"
          :data-source="record.invitees"
          row-key="invitee_telegram_id"
          :pagination="false"
          size="middle"
          class="bg-blue-50/30 my-2 rounded border border-blue-100"
        >
          <template #bodyCell="{ column, record: innerRecord }">
            <template v-if="column.key === 'commission_usdt'">
              <span class="font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded border border-indigo-100">$ {{ innerRecord.commission_usdt }}</span>
            </template>
          </template>

          <template #expandedRowRender="{ record: innerRecord }">
            <a-table
              :columns="orderColumns"
              :data-source="innerRecord.orders"
              row-key="order_id"
              :pagination="false"
              size="small"
              class="bg-white m-2 border rounded shadow-sm"
            >
              <template #bodyCell="{ column, record: orderRecord }">
                <template v-if="column.key === 'type'">
                  <a-tag :color="orderRecord.type === 'TON' ? 'blue' : (orderRecord.type === 'RMB' ? 'red' : 'orange')">
                    {{ orderRecord.type }}
                  </a-tag>
                </template>
                <template v-else-if="column.key === 'amount'">
                  <span class="font-bold">
                    {{ orderRecord.type === 'RMB' ? '¥' : '' }}
                    {{ orderRecord.amount }}
                    {{ orderRecord.type === 'TON' ? ' TON' : (orderRecord.type === 'Stars' ? ' ⭐' : '') }}
                  </span>
                </template>
              </template>
            </a-table>
          </template>
        </a-table>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
:deep(.ant-table-expanded-row) > td {
  background-color: #fafafa !important;
  padding: 8px 16px !important;
}
</style>
