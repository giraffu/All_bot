<template>
  <div class="chart-wrapper">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<script setup>
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  MarkLineComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed } from 'vue';

use([
  CanvasRenderer,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  MarkLineComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  data: {
    type: Array,
    default: () => [] // Array of {date, new_users, generations, ...}
  },
  metrics: {
    type: Array,
    default: () => ['new_users', 'new_users_all', 'generations', 'active_users', 'checkins', 'consumed_credits']
  }
});

const option = computed(() => {
  const dates = props.data.map(item => item.date);
  
  const allSeries = [
    {
      id: 'cumulative_users',
      name: '累计用户',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.cumulative_users),
      color: '#722ed1',
      smooth: true,
      areaStyle: {
        color: '#722ed1',
        opacity: 0.1
      }
    },
    {
      id: 'new_users',
      name: '新增用户',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.new_users),
      color: '#1890ff',
      areaStyle: {
        color: '#1890ff',
        opacity: 0.1
      }
    },
    {
      id: 'new_users_all',
      name: '新增用户（虚）',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.new_users_all || 0),
      color: '#722ed1',
      lineStyle: {
        type: 'dashed'
      },
      areaStyle: {
        color: '#722ed1',
        opacity: 0.1
      }
    },
    {
      id: 'generations',
      name: '生成量',
      type: 'line',
      yAxisIndex: 1,
      data: props.data.map(item => item.generations),
      color: '#52c41a',
      areaStyle: {
        color: '#52c41a',
        opacity: 0.1
      }
    },
    {
      id: 'growth_rate',
      name: '每日增长率(%)',
      type: 'line',
      yAxisIndex: 1, // Use right axis for percentage
      data: props.data.map(item => item.growth_rate || 0),
      color: '#52c41a', // Green
      lineStyle: {
        width: 2,
        type: 'dashed'
      },
      symbol: 'circle',
      symbolSize: 6,
      markLine: props.metrics.includes('growth_rate') ? {
        data: [
          {
            type: 'average',
            name: '平均增长率',
            label: {
              formatter: '平均: {c}%',
              position: 'end'
            },
            lineStyle: {
              color: '#faad14',
              type: 'dashed',
              width: 2
            }
          }
        ],
        symbol: ['none', 'none']
      } : undefined
    },
    {
      id: 'active_users',
      name: '活跃用户',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.active_users || 0),
      color: '#faad14',
      areaStyle: {
        color: '#faad14',
        opacity: 0.1
      }
    },
    {
      id: 'checkins',
      name: '签到人数',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.checkins || 0),
      color: '#13c2c2',
      areaStyle: {
        color: '#13c2c2',
        opacity: 0.1
      }
    },
    {
      id: 'consumed_credits',
      name: '消耗灵石',
      type: 'line',
      yAxisIndex: 1,
      data: props.data.map(item => item.consumed_credits || 0),
      color: '#eb2f96',
      areaStyle: {
        color: '#eb2f96',
        opacity: 0.1
      }
    },
    {
      id: 'ton_recharge',
      name: 'TON充值 (TON)',
      type: 'line',
      yAxisIndex: 1, // Change to secondary axis to not squash other lines if TON values are small
      data: props.data.map(item => item.ton_recharge || 0),
      color: '#1890ff', // Blue
      areaStyle: {
        color: '#1890ff',
        opacity: 0.1
      }
    },
    {
      id: 'stars_recharge',
      name: 'Stars充值 (Stars)',
      type: 'line',
      yAxisIndex: 0, // Stars values are large, use primary axis
      data: props.data.map(item => item.stars_recharge || 0),
      color: '#faad14', // Yellow/Gold
      areaStyle: {
        color: '#faad14',
        opacity: 0.1
      }
    }
  ];

  const visibleSeries = allSeries.filter(s => props.metrics.includes(s.id));
  
  // Determine which Y-axes are needed
  const hasAxis0 = visibleSeries.some(s => s.yAxisIndex === 0);
  const hasAxis1 = visibleSeries.some(s => s.yAxisIndex === 1);

  const yAxis = [];
  if (hasAxis0 && hasAxis1) {
    yAxis.push(
      { type: 'value', name: '人数', position: 'left' },
      { type: 'value', name: '数量', position: 'right', splitLine: { show: false } }
    );
  } else if (hasAxis0) {
    yAxis.push({ type: 'value', name: '人数', position: 'left' });
    // Update yAxisIndex for all series to 0
    visibleSeries.forEach(s => s.yAxisIndex = 0);
  } else if (hasAxis1) {
    yAxis.push({ type: 'value', name: '数量', position: 'left' });
    // Update yAxisIndex for all series to 0
    visibleSeries.forEach(s => s.yAxisIndex = 0);
  }

  return {
    title: {
      text: props.title,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: '600'
      }
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: visibleSeries.map(s => s.name),
      bottom: 'bottom'
    },
    grid: {
      left: '3%',
      right: '8%',
      bottom: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates
    },
    yAxis: yAxis,
    series: visibleSeries
  };
});
</script>

<style scoped>
.chart-wrapper {
  width: 100%;
  height: 100%;
  min-height: 400px;
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
