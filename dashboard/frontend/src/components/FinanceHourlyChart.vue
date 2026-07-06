<template>
  <DashboardChartFrame :title="props.title">
    <template #controls>
      <ComparableDateControls
        v-if="!props.showCumulativeOnly"
        :selected-dates="selectedDates"
        :format-date="formatDate"
        :get-date-color="getDateColor"
        :disabled-date="disabledDate"
        :cumulative-selected="selectedDates.includes(CUMULATIVE_DATE_KEY)"
        show-cumulative-toggle
        @add-date="handleAddDate"
        @remove-date="removeDate"
        @toggle-cumulative="toggleDateKey(CUMULATIVE_DATE_KEY)"
      />
      <a-radio-group
        v-else
        v-model:value="localTimeRange"
        button-style="solid"
        size="small"
        @change="fetchData"
      >
        <a-radio-button
          v-for="opt in props.timeRangeOptions"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </a-radio-button>
      </a-radio-group>
    </template>
    <v-chart class="chart" :option="option" autoresize :loading="loading" />
  </DashboardChartFrame>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import DashboardChartFrame from './DashboardChartFrame.vue'
import ComparableDateControls from './ComparableDateControls.vue'
import {
  CUMULATIVE_DATE_KEY,
  useComparableDates,
} from '../composables/useComparableDates'
import { fetchFinanceHourlyStats, fetchCumulativeFinanceHourlyStats } from '../api/api'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
])

interface TimeRangeOption {
  label: string
  value: number
}

type FinanceMetric = 'credits' | 'disciples'
type FinanceHourlyStats = {
  recharged_credits?: number
  inner_disciples?: number
  core_disciples?: number
  true_disciples?: number
}

const props = withDefaults(defineProps<{
  title?: string
  metric?: FinanceMetric
  colors?: string[]
  timeRange?: number
  timeRangeOptions?: TimeRangeOption[]
  showCumulativeOnly?: boolean
}>(), {
  title: '分时统计',
  metric: 'credits',
  colors: () => ['#1890ff', '#52c41a', '#faad14'],
  timeRange: 7,
  timeRangeOptions: () => [
    { label: '最近 7 天', value: 7 },
    { label: '最近 2 周', value: 14 },
    { label: '最近 1 个月', value: 30 },
    { label: '最近 2 个月', value: 60 },
    { label: '最近 3 个月', value: 90 },
    { label: '最近半年', value: 180 },
    { label: '最近 1 年', value: 365 },
  ],
  showCumulativeOnly: false,
})

const localTimeRange = ref(props.timeRange)
const hours = Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0'))

const parseFinanceHourlyStats = (rawData: Record<string, FinanceHourlyStats>) => {
  const parsedData: Record<string, number> = {}
  Object.entries(rawData).forEach(([hour, stats]) => {
    if (props.metric === 'credits') {
      parsedData[hour] = stats.recharged_credits || 0
      return
    }
    parsedData[hour] = (
      (stats.inner_disciples || 0)
      + (stats.core_disciples || 0)
      + (stats.true_disciples || 0)
    )
  })
  return parsedData
}

const {
  selectedDates,
  chartDataMap,
  loading,
  formatDate,
  getDateColor,
  disabledDate,
  fetchData,
  handleAddDate,
  removeDate,
  toggleDateKey,
} = useComparableDates<Record<string, number>>({
  initialDates: props.showCumulativeOnly
    ? [CUMULATIVE_DATE_KEY]
    : undefined,
  colors: props.colors,
  specialColors: {
    [CUMULATIVE_DATE_KEY]: '#cf1322',
  },
  formatLabel: dateKey => (
    dateKey === CUMULATIVE_DATE_KEY
      ? `累计 (${localTimeRange.value}天)`
      : dateKey.slice(5)
  ),
  loadDate: async dateKey => {
    const rawData = dateKey === CUMULATIVE_DATE_KEY
      ? await fetchCumulativeFinanceHourlyStats(localTimeRange.value)
      : await fetchFinanceHourlyStats(dateKey)
    return parseFinanceHourlyStats(rawData as Record<string, FinanceHourlyStats>)
  },
})

const formatAxisValue = (value: number) => {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`
  }
  return value
}

const option = computed(() => {
  const series = selectedDates.value.map((dateKey, index) => {
    const dataByHour = chartDataMap.value[dateKey] || {}
    const isCumulative = dateKey === CUMULATIVE_DATE_KEY
    return {
      name: formatDate(dateKey),
      type: 'bar',
      yAxisIndex: isCumulative && !props.showCumulativeOnly ? 1 : 0,
      data: hours.map(hour => dataByHour[hour] || 0),
      itemStyle: {
        color: isCumulative
          ? (props.showCumulativeOnly ? props.colors[0] : '#cf1322')
          : props.colors[index % props.colors.length],
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
      top: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: hours.map(hour => `${hour}时`),
      axisLabel: {
        interval: 1,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: props.showCumulativeOnly ? '累计新增' : '单日新增',
        position: 'left',
        splitLine: {
          lineStyle: {
            type: 'dashed',
          },
        },
        axisLabel: {
          formatter: formatAxisValue,
        },
      },
      {
        type: 'value',
        name: '累计新增',
        position: 'right',
        show: !props.showCumulativeOnly,
        splitLine: {
          show: false,
        },
        axisLabel: {
          formatter: formatAxisValue,
        },
      },
    ],
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
