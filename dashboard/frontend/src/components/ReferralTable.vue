<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchAffiliateRedeemRecords, fetchReferralRewards } from '../api/api'
import message from 'ant-design-vue/es/message'

const activeTab = ref('rewards')
const rewardsLoading = ref(false)
const redeemsLoading = ref(false)
const data = ref([])
const redeemRecords = ref([])
const redeemFilters = ref({
  query: '',
  redeemType: ''
})
const redeemPagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: total => `共 ${total} 条`
})

const loadRewardsData = async () => {
  rewardsLoading.value = true
  try {
    const res = await fetchReferralRewards()
    data.value = res
  } catch (error) {
    console.error(error)
    message.error('获取邀请奖励数据失败')
  } finally {
    rewardsLoading.value = false
  }
}

const loadRedeemData = async (
  page = redeemPagination.value.current,
  pageSize = redeemPagination.value.pageSize
) => {
  redeemsLoading.value = true
  try {
    const res = await fetchAffiliateRedeemRecords({
      page,
      pageSize,
      query: redeemFilters.value.query.trim(),
      redeemType: redeemFilters.value.redeemType
    })
    redeemRecords.value = res.items || []
    redeemPagination.value = {
      ...redeemPagination.value,
      current: res.page || page,
      pageSize: res.page_size || pageSize,
      total: res.total || 0
    }
  } catch (error) {
    console.error(error)
    message.error('获取佣金兑换记录失败')
  } finally {
    redeemsLoading.value = false
  }
}

const handleRefresh = async () => {
  if (activeTab.value === 'rewards') {
    await loadRewardsData()
    return
  }
  await loadRedeemData()
}

const handleRedeemSearch = async () => {
  await loadRedeemData(1, redeemPagination.value.pageSize)
}

const handleRedeemTableChange = async pagination => {
  await loadRedeemData(pagination.current, pagination.pageSize)
}

const handleTabChange = async key => {
  activeTab.value = key
  if (key === 'redeems' && redeemRecords.value.length === 0) {
    await loadRedeemData()
  }
}

onMounted(() => {
  loadRewardsData()
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
    title: '历史累计返佣(USDT)',
    dataIndex: 'commission_usdt',
    key: 'commission_usdt',
    width: '10%',
    sorter: (a, b) => a.commission_usdt - b.commission_usdt
  },
  {
    title: '已兑换返佣(USDT)',
    dataIndex: 'spent_commission_usdt',
    key: 'spent_commission_usdt',
    width: '10%',
    sorter: (a, b) => (a.spent_commission_usdt || 0) - (b.spent_commission_usdt || 0)
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
    title: '历史累计返佣(USDT)',
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

const redeemColumns = [
  {
    title: '用户昵称',
    dataIndex: 'user_name',
    key: 'user_name',
    width: '14%'
  },
  {
    title: '用户名',
    dataIndex: 'username',
    key: 'username',
    width: '12%'
  },
  {
    title: '用户 ID (TG)',
    dataIndex: 'user_telegram_id',
    key: 'user_telegram_id',
    width: '12%'
  },
  {
    title: '兑换时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: '14%'
  },
  {
    title: '兑换类型',
    dataIndex: 'redeem_type',
    key: 'redeem_type',
    width: '10%'
  },
  {
    title: '消耗返佣(USDT)',
    dataIndex: 'amount_usdt',
    key: 'amount_usdt',
    width: '10%'
  },
  {
    title: '兑换结果',
    dataIndex: 'redeem_result',
    key: 'redeem_result',
    width: '14%'
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: '8%'
  },
  {
    title: '记录 ID',
    dataIndex: 'redeem_id',
    key: 'redeem_id',
    width: '8%'
  }
]

</script>

<template>
  <div class="h-full flex flex-col">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-xl font-bold text-gray-800 m-0">邀请返佣历史榜与充值数据分析</h2>
      <a-button type="primary" @click="handleRefresh" :loading="activeTab === 'rewards' ? rewardsLoading : redeemsLoading">
        刷新数据
      </a-button>
    </div>

    <a-tabs :active-key="activeTab" @change="handleTabChange">
      <a-tab-pane key="rewards" tab="邀请返佣榜">
        <a-row :gutter="16" class="mb-4">
          <a-col :span="12">
            <a-card class="shadow-sm border border-gray-100 h-full">
              <div class="flex justify-around items-center">
                <a-statistic title="有历史返佣的邀请人" :value="summaryStats.rewardedInvitersCount" />
                <a-statistic title="历史累计返佣 (USDT)" :value="summaryStats.totalCommission" prefix="$" />
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
          :loading="rewardsLoading"
          :pagination="{ pageSize: 20 }"
          class="flex-1 bg-white rounded-lg shadow-sm overflow-hidden border border-gray-100"
        >
          <template #title>
            <div class="text-slate-500 text-sm">
              当前表格展示的是邀请返佣历史累计成绩，不是“当前可兑换余额”面板。
            </div>
          </template>
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
            <template v-else-if="column.key === 'spent_commission_usdt'">
              <span class="font-bold text-rose-600 bg-rose-50 px-2 py-1 rounded border border-rose-100">$ {{ record.spent_commission_usdt || 0 }}</span>
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
      </a-tab-pane>

      <a-tab-pane key="redeems" tab="佣金兑换记录">
        <a-card class="mb-4 border border-gray-100 shadow-sm">
          <div class="flex flex-wrap gap-3 items-center">
            <a-input
              v-model:value="redeemFilters.query"
              placeholder="搜索昵称 / 用户名 / TG ID / 用户ID"
              class="w-72"
              allow-clear
              @pressEnter="handleRedeemSearch"
            />
            <a-select
              v-model:value="redeemFilters.redeemType"
              placeholder="兑换类型"
              allow-clear
              class="w-40"
            >
              <a-select-option value="CREDITS">兑灵石</a-select-option>
              <a-select-option value="MEMBERSHIP">兑身份</a-select-option>
            </a-select>
            <a-button type="primary" @click="handleRedeemSearch" :loading="redeemsLoading">
              查询
            </a-button>
          </div>
        </a-card>

        <a-table
          :columns="redeemColumns"
          :data-source="redeemRecords"
          row-key="redeem_id"
          :loading="redeemsLoading"
          :pagination="redeemPagination"
          class="flex-1 bg-white rounded-lg shadow-sm overflow-hidden border border-gray-100"
          @change="handleRedeemTableChange"
        >
          <template #title>
            <div class="text-slate-500 text-sm">
              展示用户佣金兑换灵石 / 兑换身份的后台记录，可按用户检索。
            </div>
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'username'">
              <span class="text-blue-500">{{ record.username ? `@${record.username}` : '-' }}</span>
            </template>
            <template v-else-if="column.key === 'redeem_type'">
              <a-tag :color="record.redeem_type === 'MEMBERSHIP' ? 'gold' : 'blue'">
                {{ record.redeem_type === 'MEMBERSHIP' ? '兑身份' : '兑灵石' }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'amount_usdt'">
              <span class="font-bold text-red-500">- $ {{ Number(record.amount_usdt || 0).toFixed(4) }}</span>
            </template>
            <template v-else-if="column.key === 'redeem_result'">
              <div v-if="record.redeem_type === 'MEMBERSHIP'" class="flex flex-col">
                <span class="font-medium text-amber-700">{{ record.target_identity || '-' }}</span>
                <span class="text-xs text-slate-500">{{ record.duration_days ? `${record.duration_days} 天` : '-' }}</span>
                <span class="text-xs text-emerald-600" v-if="record.credits_granted">+{{ record.credits_granted }} 灵石</span>
              </div>
              <div v-else class="flex flex-col">
                <span class="font-medium text-emerald-600">+{{ record.credits_granted }} 灵石</span>
                <span class="text-xs text-slate-500">{{ record.redeem_option_key }}</span>
              </div>
            </template>
            <template v-else-if="column.key === 'status'">
              <a-tag :color="record.status === 'SUCCESS' ? 'green' : 'default'">{{ record.status }}</a-tag>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<style scoped>
:deep(.ant-table-expanded-row) > td {
  background-color: #fafafa !important;
  padding: 8px 16px !important;
}
</style>
