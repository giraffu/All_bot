<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchFinanceHistory } from '../api/api'
import StatsCards from './StatsCards.vue'
import LineChart from './LineChart.vue'
import FinanceHourlyChart from './FinanceHourlyChart.vue'
import RmbChannelSummary from './RmbChannelSummary.vue'

interface TimeRangeOption { label: string, value: number }
interface FinanceStats { rmb_balance?: number, rmb_channels?: Record<string, { amount: number, orders: number }>, [key: string]: unknown }
const props = defineProps<{ stats: FinanceStats, statsHistory: Record<string, any>[], historyTimeRange: number, timeRangeOptions: TimeRangeOption[] }>()

const emit = defineEmits(['update:historyTimeRange', 'loadHistory'])

const updateHistoryTimeRange = (value: number) => {
  emit('update:historyTimeRange', value)
  emit('loadHistory')
}

const rechargedCreditsTimeRange = ref(7)
const rechargedCreditsHistory = ref<Record<string, any>[]>([])

const disciplesTimeRange = ref(7)
const disciplesHistory = ref<Record<string, any>[]>([])

const loadRechargedCreditsHistory = async () => {
  if (rechargedCreditsTimeRange.value === props.historyTimeRange && props.statsHistory.length) {
    rechargedCreditsHistory.value = props.statsHistory;
    return;
  }
  try {
    rechargedCreditsHistory.value = await fetchFinanceHistory(rechargedCreditsTimeRange.value)
  } catch (err) {
    console.error(err)
  }
}

const loadDisciplesHistory = async () => {
  if (disciplesTimeRange.value === props.historyTimeRange && props.statsHistory.length) {
    disciplesHistory.value = props.statsHistory;
    return;
  }
  try {
    disciplesHistory.value = await fetchFinanceHistory(disciplesTimeRange.value)
  } catch (err) {
    console.error(err)
  }
}

watch(rechargedCreditsTimeRange, loadRechargedCreditsHistory)
watch(disciplesTimeRange, loadDisciplesHistory)

watch(() => props.statsHistory, (newVal) => {
  if (rechargedCreditsTimeRange.value === props.historyTimeRange) {
    rechargedCreditsHistory.value = newVal;
  }
  if (disciplesTimeRange.value === props.historyTimeRange) {
    disciplesHistory.value = newVal;
  }
}, { immediate: true })

</script>

<template>
  <div class="flex-1 flex flex-col gap-6">
    <StatsCards :stats="stats" mode="finance" />
    <RmbChannelSummary class="finance-rmb-breakdown" :total="stats.rmb_balance || 0" :channels="stats.rmb_channels || {}" />

    <div class="flex flex-col gap-6">
      <div class="flex items-center justify-between px-2">
        <h3 class="text-lg font-semibold text-gray-800 m-0">财务历史趋势 (最近 {{ historyTimeRange }} 天)</h3>
        <a-radio-group 
          :value="historyTimeRange" 
          @update:value="updateHistoryTimeRange"
          button-style="solid"
          size="small"
        >
          <a-radio-button 
            v-for="opt in timeRangeOptions" 
            :key="opt.value" 
            :value="opt.value"
          >
            {{ opt.label }}
          </a-radio-button>
        </a-radio-group>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div class="h-80">
          <LineChart title="每日充值 (TON)" :data="statsHistory" :metrics="['ton_recharge', 'cumulative_ton']" />
        </div>
        <div class="h-80">
          <LineChart title="每日充值 (Stars)" :data="statsHistory" :metrics="['stars_recharge', 'cumulative_stars']" />
        </div>
        <div class="h-80">
          <LineChart title="每日充值 (RMB · 按渠道)" :data="statsHistory" :metrics="['rmb_direct_alipay', 'rmb_collected_alipay', 'rmb_collected_wechat', 'rmb_legacy_unclassified', 'cumulative_rmb']" />
        </div>
      </div>
      
      <div class="grid grid-cols-1 gap-6 mb-10">
        <div class="h-96">
          <LineChart title="每日充值 (USDT)" :data="statsHistory" :metrics="['usdt_recharge', 'cumulative_usdt']" />
        </div>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-1 gap-6 mb-10">
        <div class="h-96 lg:col-span-1">
          <LineChart :data="rechargedCreditsHistory" :metrics="['recharged_credits', 'cumulative_recharged_credits']">
            <template #header>
              <div class="flex items-center justify-between px-2">
                <h3 class="text-base font-semibold text-gray-700 m-0">每日充值直充灵石趋势 (最近 {{ rechargedCreditsTimeRange }} 天)</h3>
                <a-radio-group 
                  v-model:value="rechargedCreditsTimeRange"
                  button-style="solid"
                  size="small"
                >
                  <a-radio-button 
                    v-for="opt in timeRangeOptions" 
                    :key="opt.value" 
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </a-radio-button>
                </a-radio-group>
              </div>
            </template>
          </LineChart>
        </div>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
        <div class="h-96 lg:col-span-1">
          <FinanceHourlyChart title="分时充值直充灵石" metric="credits" :timeRange="rechargedCreditsTimeRange" :colors="['#13c2c2', '#08979c', '#faad14']" />
        </div>
        <div class="h-96 lg:col-span-1">
          <FinanceHourlyChart title="累计分时充值直充灵石" metric="credits" :timeRange="rechargedCreditsTimeRange" :timeRangeOptions="timeRangeOptions" :colors="['#13c2c2', '#08979c', '#faad14']" :showCumulativeOnly="true" />
        </div>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-1 gap-6 mb-6">
        <div class="h-96 lg:col-span-1">
          <LineChart :data="disciplesHistory" :metrics="['inner_disciples', 'core_disciples', 'true_disciples']">
            <template #header>
              <div class="flex items-center justify-between px-2">
                <h3 class="text-base font-semibold text-gray-700 m-0">每日增加弟子数量趋势 (最近 {{ disciplesTimeRange }} 天)</h3>
                <a-radio-group 
                  v-model:value="disciplesTimeRange"
                  button-style="solid"
                  size="small"
                >
                  <a-radio-button 
                    v-for="opt in timeRangeOptions" 
                    :key="opt.value" 
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </a-radio-button>
                </a-radio-group>
              </div>
            </template>
          </LineChart>
        </div>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div class="h-96 lg:col-span-1">
          <FinanceHourlyChart title="分时增加弟子数量" metric="disciples" :timeRange="disciplesTimeRange" :colors="['#1890ff', '#722ed1', '#eb2f96']" />
        </div>
        <div class="h-96 lg:col-span-1">
          <FinanceHourlyChart title="累计分时增加弟子数量" metric="disciples" :timeRange="disciplesTimeRange" :timeRangeOptions="timeRangeOptions" :colors="['#722ed1', '#1890ff', '#eb2f96']" :showCumulativeOnly="true" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 767px) {
  .finance-rmb-breakdown {
    order: -1;
  }
}
</style>
