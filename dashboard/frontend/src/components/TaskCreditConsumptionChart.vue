<template>
  <DashboardChartFrame :title="props.title">
    <template #controls>
      <ComparableDateControls
        :selected-dates="selectedDates"
        :format-date="formatDate"
        :get-date-color="getDateColor"
        :disabled-date="disabledDate"
        placeholder="添加对比"
        picker-width="100px"
        @add-date="handleAddDate"
        @remove-date="removeDate"
      />
    </template>
    <div class="chart-stack">
      <v-chart class="chart" :option="option" autoresize :loading="loading" />
      <p class="chart-note">按任务扣费流水统计；展示提交时实际扣除的灵石，不重复计算内部阶段。</p>
    </div>
  </DashboardChartFrame>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import DashboardChartFrame from './DashboardChartFrame.vue'
import ComparableDateControls from './ComparableDateControls.vue'
import { useComparableDates } from '../composables/useComparableDates'
import { fetchTaskCreditDistribution } from '../api/api'
import { buildCreditConsumptionPieData } from '../utils/taskAnalyticsCharts'

use([CanvasRenderer, PieChart, LegendComponent, TitleComponent, TooltipComponent])

const props = withDefaults(defineProps<{ title?: string }>(), {
  title: '生成类型灵石消耗',
})

type CreditResponse = {
  date: string
  unit: string
  basis: string
  total_credits: number
  values: Record<string, number>
}

const {
  selectedDates,
  chartDataMap,
  loading,
  formatDate,
  getDateColor,
  disabledDate,
  handleAddDate,
  removeDate,
} = useComparableDates<CreditResponse>({
  loadDate: async dateKey => fetchTaskCreditDistribution(dateKey) as Promise<CreditResponse>,
})

const pieGeometry = (count: number) => {
  if (count === 1) return { centers: [['60%', '48%']], radius: ['38%', '66%'] }
  if (count === 2) return { centers: [['38%', '48%'], ['78%', '48%']], radius: ['27%', '46%'] }
  return { centers: [['28%', '48%'], ['59%', '48%'], ['88%', '48%']], radius: ['22%', '36%'] }
}

const option = computed(() => {
  const count = selectedDates.value.length
  if (!count) return {}
  const { centers, radius } = pieGeometry(count)
  return {
    title: selectedDates.value.map((dateKey, index) => ({
      text: formatDate(dateKey),
      left: centers[index][0],
      top: '82%',
      textAlign: 'center',
      textStyle: { fontSize: 13, fontWeight: 'normal' },
    })),
    tooltip: {
      trigger: 'item',
      formatter: ({ seriesName, data, percent }: any) => (
        `${seriesName}<br/>${data.name}: <b>${Number(data.value).toLocaleString()}</b> 灵石 (${percent}%)`
      ),
    },
    legend: { orient: 'vertical', top: 'middle', left: 'left', type: 'scroll' },
    series: selectedDates.value.map((dateKey, index) => ({
      name: formatDate(dateKey),
      type: 'pie',
      radius,
      center: centers[index],
      data: buildCreditConsumptionPieData(chartDataMap.value[dateKey]),
      label: { show: false },
      labelLine: { show: false },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.35)',
        },
      },
    })),
  }
})
</script>

<style scoped>
.chart-stack { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.chart { flex: 1 1 auto; min-height: 0; width: 100%; }
.chart-note { flex: 0 0 auto; margin: 4px 0 0; color: #8c8c8c; font-size: 12px; line-height: 1.4; }
</style>
