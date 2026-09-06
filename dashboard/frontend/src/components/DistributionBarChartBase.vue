<template>
  <div class="chart-wrapper relative flex flex-col">
    <div class="mb-4 flex items-center justify-between px-2">
      <div class="text-base font-bold">{{ title }}</div>
    </div>
    <div class="min-h-0 flex-1">
      <v-chart class="chart" :option="option" autoresize />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import type { EChartsOption } from 'echarts';

use([CanvasRenderer, BarChart, TooltipComponent, GridComponent]);

interface Props {
  title: string;
  data: Record<string, number>;
  categories: string[];
  xAxisName: string;
  tooltipFormatter: string;
  color: string;
  axisLabelRotation?: number;
}

const props = withDefaults(defineProps<Props>(), {
  axisLabelRotation: 0
});

const option = computed<EChartsOption>(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: props.tooltipFormatter
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
    data: props.categories,
    name: props.xAxisName,
    nameLocation: 'end',
    axisLabel: {
      interval: 0,
      rotate: props.axisLabelRotation
    }
  },
  yAxis: {
    type: 'value',
    name: '用户数',
    splitLine: { lineStyle: { type: 'dashed' } }
  },
  series: [{
    name: '用户数量',
    type: 'bar',
    data: props.categories.map((category) => props.data[category] ?? 0),
    itemStyle: {
      color: props.color,
      borderRadius: [4, 4, 0, 0]
    },
    label: { show: true, position: 'top' },
    barMaxWidth: 50
  }]
}));
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
