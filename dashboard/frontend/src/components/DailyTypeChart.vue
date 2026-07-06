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
    <v-chart class="chart" :option="option" autoresize :loading="loading" />
  </DashboardChartFrame>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import DashboardChartFrame from './DashboardChartFrame.vue'
import ComparableDateControls from './ComparableDateControls.vue'
import { useComparableDates } from '../composables/useComparableDates'
import { fetchTypeDistribution } from '../api/api'
import { TASK_TYPE_COLORS, TASK_TYPE_LABELS } from '../constants/taskTypes'

use([
  CanvasRenderer,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
])

const props = withDefaults(defineProps<{
  title?: string
  donut?: boolean
}>(), {
  title: '生成类型分布',
  donut: false,
})

type TypeDistribution = Record<string, number>

const {
  selectedDates,
  chartDataMap,
  loading,
  formatDate,
  getDateColor,
  disabledDate,
  handleAddDate,
  removeDate,
} = useComparableDates<TypeDistribution>({
  loadDate: async dateKey => fetchTypeDistribution(dateKey) as Promise<TypeDistribution>,
})

const getTransformData = (dateKey: string) => {
  const data = chartDataMap.value[dateKey]
  if (!data) return []
  return Object.entries(data).map(([key, value]) => ({
    name: (TASK_TYPE_LABELS as Record<string, string>)[key] || key,
    value,
    itemStyle: {
      color: (TASK_TYPE_COLORS as Record<string, string>)[key] || undefined,
    },
  }))
}

const option = computed(() => {
  const count = selectedDates.value.length
  if (count === 0) return {}

  const titles: Array<Record<string, unknown>> = []
  const series: Array<Record<string, unknown>> = []
  let centers: Array<[string, string]> = []
  let radius: string | [string, string] = props.donut ? ['30%', '50%'] : '50%'

  if (count === 1) {
    centers = [['60%', '50%']]
    radius = props.donut ? ['40%', '70%'] : '60%'
  } else if (count === 2) {
    centers = [['40%', '50%'], ['80%', '50%']]
    radius = props.donut ? ['30%', '50%'] : '45%'
  } else if (count === 3) {
    centers = [['30%', '50%'], ['60%', '50%'], ['90%', '50%']]
    radius = props.donut ? ['25%', '40%'] : '35%'
  }

  selectedDates.value.forEach((dateKey, index) => {
    titles.push({
      text: formatDate(dateKey),
      left: centers[index][0],
      top: '85%',
      textAlign: 'center',
      textStyle: {
        fontSize: 14,
        fontWeight: 'normal',
      },
    })

    series.push({
      name: formatDate(dateKey),
      type: 'pie',
      radius,
      center: centers[index],
      data: getTransformData(dateKey),
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)',
        },
      },
      label: {
        show: false,
      },
      labelLine: {
        show: false,
      },
    })
  })

  return {
    title: titles,
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      top: 'middle',
      left: 'left',
      type: 'scroll',
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
