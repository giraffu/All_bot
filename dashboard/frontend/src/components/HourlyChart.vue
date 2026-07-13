<template>
  <DashboardChartFrame :title="props.title">
    <template #controls>
      <ComparableDateControls
        :selected-dates="selectedDates"
        :format-date="formatDate"
        :get-date-color="getDateColor"
        :disabled-date="disabledDate"
        @add-date="handleAddDate"
        @remove-date="removeDate"
      />
    </template>
    <v-chart class="chart" :option="option" autoresize :loading="loading" />
  </DashboardChartFrame>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import DashboardChartFrame from './DashboardChartFrame.vue'
import ComparableDateControls from './ComparableDateControls.vue'
import { useComparableDates } from '../composables/useComparableDates'
import { fetchHourlyStats } from '../api/api'

use([
  CanvasRenderer,
  BarChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
])

const props = withDefaults(defineProps<{
  title?: string
}>(), {
  title: '分时生成量',
})

const colors = ['#1890ff', '#52c41a', '#faad14']
const hours = Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0'))

const {
  selectedDates,
  chartDataMap,
  loading,
  formatDate,
  getDateColor,
  disabledDate,
  handleAddDate,
  removeDate,
} = useComparableDates<Record<string, number>>({
  colors,
  loadDate: async dateKey => fetchHourlyStats(dateKey) as Promise<Record<string, number>>,
})

const option = computed(() => {
  const series = selectedDates.value.map((dateKey, index) => {
    const dataByHour = chartDataMap.value[dateKey] || {}
    return {
      name: formatDate(dateKey),
      type: 'bar',
      data: hours.map(hour => dataByHour[hour] || 0),
      itemStyle: {
        color: colors[index % colors.length],
        borderRadius: [4, 4, 0, 0],
      },
      emphasis: {
        focus: 'series',
      },
      barMaxWidth: 20,
    }
  })

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    legend: {
      data: selectedDates.value.map(dateKey => formatDate(dateKey)),
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: hours.map(hour => `${hour}时`),
      axisLabel: {
        interval: 1,
      },
    },
    yAxis: {
      type: 'value',
      splitLine: {
        lineStyle: {
          type: 'dashed',
        },
      },
    },
    series,
  }
})
</script>

<style scoped>
.chart {
  height: 100%;
  width: 100%;
}
</style>
