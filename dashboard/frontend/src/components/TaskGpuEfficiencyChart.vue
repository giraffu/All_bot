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
      <p class="chart-note">GPU 小时按每笔任务 running → gpu_done 实测，并以实际执行 Worker 的显卡折算为 RTX 5090；{{ coverageText }}</p>
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
import { fetchTaskGpuEfficiency } from '../api/api'
import { buildGpuEfficiencyPieData } from '../utils/taskAnalyticsCharts'

use([CanvasRenderer, PieChart, LegendComponent, TitleComponent, TooltipComponent])

const props = withDefaults(defineProps<{ title?: string }>(), {
  title: '任务灵石效率（5090 等效）',
})

type EfficiencyItem = {
  value: number
  credits: number
  gross_credits: number
  gpu_hours: number
  task_count: number
  successful_task_count: number
  worker_count: number
  telemetry_coverage: number
  estimated: boolean
  gpu_time_source: string
}

type EfficiencyResponse = {
  date: string
  unit: string
  calibration: string
  items: Record<string, EfficiencyItem>
  total_credits: number
  covered_credits: number
  uncovered_credits: number
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
} = useComparableDates<EfficiencyResponse>({
  loadDate: async dateKey => fetchTaskGpuEfficiency(dateKey) as Promise<EfficiencyResponse>,
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
      formatter: ({ seriesName, data }: any) => [
        seriesName,
        `${data.name}: <b>${Number(data.value).toLocaleString()}</b> 灵石/GPU·小时`,
        `精确任务 ${Number(data.taskCount).toLocaleString()} / 成功任务 ${Number(data.successfulTaskCount).toLocaleString()} 笔`,
        `实际执行 Worker ${Number(data.workerCount).toLocaleString()} 个`,
        `归因灵石 ${Number(data.credits).toLocaleString()} / 当日总灵石 ${Number(data.grossCredits).toLocaleString()}`,
        `5090 等效 GPU ${Number(data.gpuHours).toFixed(3)} 小时`,
        `执行阶段覆盖 ${(Number(data.telemetryCoverage) * 100).toFixed(1)}%`,
        data.estimated ? '灵石按精确任务覆盖率同比例归因' : '全量任务精确归因',
      ].filter(Boolean).join('<br/>'),
    },
    legend: { orient: 'vertical', top: 'middle', left: 'left', type: 'scroll' },
    series: selectedDates.value.map((dateKey, index) => ({
      name: formatDate(dateKey),
      type: 'pie',
      radius,
      center: centers[index],
      data: buildGpuEfficiencyPieData(chartDataMap.value[dateKey]),
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

const coverageText = computed(() => selectedDates.value.map((dateKey) => {
  const data = chartDataMap.value[dateKey]
  if (!data || data.total_credits <= 0) return `${formatDate(dateKey)} 暂无扣费数据`
  const percent = (data.covered_credits / data.total_credits * 100).toFixed(1)
  return `${formatDate(dateKey)} 精确归因 ${percent}%（未覆盖 ${data.uncovered_credits.toLocaleString()} 灵石）`
}).join('；'))
</script>

<style scoped>
.chart-stack { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.chart { flex: 1 1 auto; min-height: 0; width: 100%; }
.chart-note { flex: 0 0 auto; margin: 4px 0 0; color: #8c8c8c; font-size: 12px; line-height: 1.4; }
</style>
