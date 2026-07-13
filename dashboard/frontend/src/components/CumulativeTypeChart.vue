<template>
  <DashboardChartFrame :title="props.title">
    <template #controls>
      <a-radio-group 
        v-model:value="timeRange" 
        @change="handleRangeChange"
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
    </template>
    <v-chart class="chart" :option="option" autoresize :loading="loading" />
  </DashboardChartFrame>
</template>

<script setup lang="ts">
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { PieChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed, ref, onMounted } from 'vue';
import DashboardChartFrame from './DashboardChartFrame.vue';
import { fetchCumulativeTypeDistribution } from '../api/api';
import { TASK_TYPE_COLORS, TASK_TYPE_LABELS } from '../constants/taskTypes';

use([
  CanvasRenderer,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent
]);

const props = withDefaults(defineProps<{
  title?: string
  donut?: boolean
}>(), {
  title: '累计生成类型分布',
  donut: false
});

const timeRangeOptions = [
  { label: '3天', value: 3 },
  { label: '1周', value: 7 },
  { label: '2周', value: 14 },
  { label: '1月', value: 30 },
  { label: '3月', value: 90 },
  { label: '半年', value: 180 },
  { label: '1年', value: 365 }
];

const timeRange = ref<number>(7);
const loading = ref(false);
const chartData = ref<Record<string, number>>({});

const fetchData = async () => {
  loading.value = true;
  try {
    const data = await fetchCumulativeTypeDistribution(timeRange.value);
    chartData.value = data as Record<string, number>;
  } catch (error) {
    console.error('Failed to fetch cumulative type distribution:', error);
  } finally {
    loading.value = false;
  }
};

const handleRangeChange = () => {
  fetchData();
};

onMounted(() => {
  fetchData();
});

const transformedData = computed(() => {
  if (!chartData.value) return [];
  return Object.entries(chartData.value).map(([key, value]) => ({
    name: (TASK_TYPE_LABELS as Record<string, string>)[key] || key,
    value: value,
    itemStyle: {
      color: (TASK_TYPE_COLORS as Record<string, string>)[key] || undefined
    }
  }));
});

const option = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} ({d}%)'
  },
  legend: {
    orient: 'vertical',
    left: 'left',
    type: 'scroll'
  },
  series: [
    {
      name: props.title,
      type: 'pie',
      radius: props.donut ? ['40%', '70%'] : '50%',
      center: ['60%', '50%'], // Adjust center to make room for legend
      data: transformedData.value,
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      label: {
        show: false
      },
      labelLine: {
        show: false
      }
    }
  ]
}));
</script>

<style scoped>
.chart {
  height: 100%;
  width: 100%;
}
</style>
