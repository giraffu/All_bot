<script setup>
import { computed } from 'vue'
import StatsCards from './StatsCards.vue'
import DailyTypeChart from './DailyTypeChart.vue'
import HourlyChart from './HourlyChart.vue'
import CumulativeTypeChart from './CumulativeTypeChart.vue'
import CumulativeHourlyChart from './CumulativeHourlyChart.vue'
import GenerationDistributionChart from './GenerationDistributionChart.vue'
import AvgDailyDistributionChart from './AvgDailyDistributionChart.vue'
import CreditDistributionChart from './CreditDistributionChart.vue'
import AvgDailyCreditDistributionChart from './AvgDailyCreditDistributionChart.vue'
import CreditHoldingDistributionChart from './CreditHoldingDistributionChart.vue'
import UserGroupDistributionChart from './UserGroupDistributionChart.vue'
import LineChart from './LineChart.vue'

const props = defineProps({
  stats: {
    type: Object,
    required: true
  },
  statsHistory: {
    type: Array,
    required: true
  },
  cumulativeStatsHistory: {
    type: Array,
    required: true
  },
  historyTimeRange: {
    type: Number,
    required: true
  },
  timeRangeOptions: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['update:historyTimeRange', 'loadHistory'])

const updateHistoryTimeRange = (value) => {
  emit('update:historyTimeRange', value)
  emit('loadHistory')
}
</script>

<template>
  <div class="flex-1 flex flex-col gap-6">
    <StatsCards :stats="stats" mode="user" />
    
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="h-80">
        <DailyTypeChart title="生成类型分布" donut />
      </div>
      <div class="h-80">
        <HourlyChart title="分时生成量" />
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="h-80">
        <CumulativeTypeChart title="累计生成类型分布" donut />
      </div>
      <div class="h-80">
        <CumulativeHourlyChart title="累计分时生成量" />
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="h-80">
        <GenerationDistributionChart title="用户生成量分布" :data="stats.generation_distribution" />
      </div>
      <div class="h-80">
        <AvgDailyDistributionChart title="用户日均生成量分布" :data="stats.avg_daily_distribution" />
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="h-80">
        <CreditDistributionChart title="用户积分消耗分布" :data="stats.credit_distribution" />
      </div>
      <div class="h-80">
        <AvgDailyCreditDistributionChart title="用户日均积分消耗分布" :data="stats.avg_daily_credit_distribution" />
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="h-80">
        <CreditHoldingDistributionChart title="用户持有积分分布" :data="stats.credit_holding_distribution" />
      </div>
      <div class="h-80">
        <UserGroupDistributionChart title="用户修为分布" :data="stats.user_group_distribution" />
      </div>
    </div>

    <div class="flex flex-col gap-6">
      <div class="flex items-center justify-between px-2">
        <h3 class="text-lg font-semibold text-gray-800 m-0">历史趋势 (最近 {{ historyTimeRange }} 天)</h3>
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

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div class="h-80">
          <LineChart title="用户增长 (每日)" :data="statsHistory" :metrics="['new_users', 'new_users_all']" />
        </div>
        <div class="h-80">
          <LineChart title="用户每日增长率" :data="statsHistory" :metrics="['growth_rate']" />
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div class="h-80">
          <LineChart title="总用户数量" :data="cumulativeStatsHistory" :metrics="['cumulative_users']" />
        </div>
        <div class="h-80">
          <LineChart title="活跃与签到" :data="statsHistory" :metrics="['active_users', 'checkins']" />
        </div>
      </div>
      
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="h-80">
          <LineChart title="生成量与灵石消耗" :data="statsHistory" :metrics="['generations', 'consumed_credits']" />
        </div>
      </div>
    </div>
  </div>
</template>
