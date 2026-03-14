<template>
  <div class="chart-wrapper relative flex flex-col">
    <div class="flex justify-between items-center mb-4 px-2">
      <div class="font-bold text-base">{{ props.title }}</div>
    </div>
    <div class="flex-1 min-h-0">
      <v-chart class="chart" :option="option" autoresize />
    </div>
  </div>
</template>

<script setup>
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  GridComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed } from 'vue';

use([
  CanvasRenderer,
  BarChart,
  TitleComponent,
  TooltipComponent,
  GridComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: '用户日均积分消耗分布'
  },
  data: {
    type: Object,
    default: () => ({})
  }
});

const categories = [
  '0', '0-1', '1-5', '5-10', '10-20', '20-50', '50+'
];

const option = computed(() => {
  const values = categories.map(cat => props.data[cat] || 0);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      },
      formatter: '{b} 积分/天: {c} 人'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: categories,
      name: '积分/天',
      nameLocation: 'end',
      axisLabel: {
        interval: 0
      }
    },
    yAxis: {
      type: 'value',
      name: '用户数',
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: '用户数量',
        type: 'bar',
        data: values,
        itemStyle: {
          color: '#f5222d', // Red color
          borderRadius: [4, 4, 0, 0]
        },
        label: {
          show: true,
          position: 'top'
        },
        barMaxWidth: 50
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