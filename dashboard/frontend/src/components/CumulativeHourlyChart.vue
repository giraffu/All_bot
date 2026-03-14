<template>
  <div class="chart-wrapper flex flex-col">
    <div class="flex justify-between items-center mb-4 shrink-0">
      <h3 class="text-base font-semibold text-gray-800 m-0">{{ props.title }}</h3>
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
    </div>
    <div class="flex-1 min-h-0">
      <v-chart class="chart" :option="option" autoresize :loading="loading" />
    </div>
  </div>
</template>

<script setup>
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart } from 'echarts/charts';
import {
  TooltipComponent,
  GridComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed, ref, onMounted } from 'vue';
import { fetchCumulativeHourlyStats } from '../api/api';

use([
  CanvasRenderer,
  BarChart,
  TooltipComponent,
  GridComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: '累计分时生成量'
  }
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

const timeRange = ref(7); // Default 7 days
const loading = ref(false);
const chartData = ref({});

const fetchData = async () => {
  loading.value = true;
  try {
    const data = await fetchCumulativeHourlyStats(timeRange.value);
    chartData.value = data;
  } catch (error) {
    console.error('Failed to fetch cumulative hourly stats:', error);
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

const option = computed(() => {
  const hours = Object.keys(chartData.value).sort();
  const counts = hours.map(h => chartData.value[h]);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      },
      formatter: (params) => {
        const item = params[0];
        return `${item.name}时: <span style="font-weight: bold; color: #722ed1">${item.value}</span> 次生成`;
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '5%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: hours.map(h => `${h}`),
      axisLabel: {
        interval: 1
      }
    },
    yAxis: {
      type: 'value',
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: '累计生成量',
        type: 'bar',
        data: counts,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#722ed1' }, // Top color (Purple)
              { offset: 1, color: '#b37feb' }  // Bottom color
            ]
          },
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          itemStyle: {
            color: '#531dab'
          }
        }
      }
    ]
  };
});
</script>

<style scoped>
.chart-wrapper {
  width: 100%;
  height: 100%;
  min-height: 300px;
  background: white;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #f0f0f0;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
}

.chart {
  height: 100%;
  width: 100%;
}
</style>
