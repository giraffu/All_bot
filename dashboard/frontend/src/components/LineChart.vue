<template>
  <div class="chart-wrapper flex flex-col">
    <div v-if="$slots.header" class="mb-4">
      <slot name="header"></slot>
    </div>
    <div class="flex-1 min-h-0">
      <v-chart class="chart" :option="option" autoresize />
    </div>
  </div>
</template>

<script setup>
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, BarChart } from 'echarts/charts';
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
  BarChart,
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
      id: 'web_active_users',
      name: 'Web活跃用户',
      type: 'line',
      yAxisIndex: 0,
      data: props.data.map(item => item.web_active_users || 0),
      color: '#ff7a45',
      areaStyle: {
        color: '#ff7a45',
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
      name: '每日充值 (TON)',
      type: 'bar',
      yAxisIndex: 0, 
      data: props.data.map(item => item.ton_recharge || 0),
      color: '#1890ff', 
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'cumulative_ton',
      name: '累计充值 (TON)',
      type: 'line',
      yAxisIndex: 1, 
      data: props.data.map(item => item.cumulative_ton || 0),
      color: '#096dd9', 
      smooth: true,
      lineStyle: {
        width: 3
      },
      symbol: 'none',
      areaStyle: {
        color: '#1890ff',
        opacity: 0.05
      }
    },
    {
      id: 'stars_recharge',
      name: '每日充值 (Stars)',
      type: 'bar',
      yAxisIndex: 0, 
      data: props.data.map(item => item.stars_recharge || 0),
      color: '#faad14', 
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'cumulative_stars',
      name: '累计充值 (Stars)',
      type: 'line',
      yAxisIndex: 1, 
      data: props.data.map(item => item.cumulative_stars || 0),
      color: '#d48806', 
      smooth: true,
      lineStyle: {
        width: 3
      },
      symbol: 'none',
      areaStyle: {
        color: '#faad14',
        opacity: 0.05
      }
    },
    {
      id: 'rmb_recharge',
      name: '每日充值 (RMB)',
      type: 'bar',
      yAxisIndex: 0, 
      data: props.data.map(item => item.rmb_recharge || 0),
      color: '#f5222d', 
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'cumulative_rmb',
      name: '累计充值 (RMB)',
      type: 'line',
      yAxisIndex: 1, 
      data: props.data.map(item => item.cumulative_rmb || 0),
      color: '#cf1322', 
      smooth: true,
      lineStyle: {
        width: 3
      },
      symbol: 'none',
      areaStyle: {
        color: '#f5222d',
        opacity: 0.05
      }
    },
    {
      id: 'inner_disciples',
      name: '每日增加内门',
      type: 'bar',
      yAxisIndex: 0,
      data: props.data.map(item => item.inner_disciples || 0),
      color: '#1890ff',
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'core_disciples',
      name: '每日增加核心',
      type: 'bar',
      yAxisIndex: 0,
      data: props.data.map(item => item.core_disciples || 0),
      color: '#722ed1',
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'true_disciples',
      name: '每日增加真传',
      type: 'bar',
      yAxisIndex: 0,
      data: props.data.map(item => item.true_disciples || 0),
      color: '#eb2f96',
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'recharged_credits',
      name: '每日新增直充灵石',
      type: 'bar',
      yAxisIndex: 0,
      data: props.data.map(item => item.recharged_credits || 0),
      color: '#13c2c2',
      itemStyle: {
        borderRadius: [4, 4, 0, 0]
      }
    },
    {
      id: 'cumulative_recharged_credits',
      name: '累计直充灵石',
      type: 'line',
      yAxisIndex: 1,
      data: props.data.map(item => item.cumulative_recharged_credits || 0),
      color: '#08979c',
      smooth: true,
      lineStyle: {
        width: 3
      },
      symbol: 'none',
      areaStyle: {
        color: '#13c2c2',
        opacity: 0.05
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
      { type: 'value', name: '每日新增', position: 'left' },
      { 
        type: 'value', 
        name: '累计充值总额', 
        position: 'right', 
        splitLine: { show: false },
        axisLabel: {
          formatter: (value) => {
            if (value >= 1000000) {
              return (value / 1000000).toFixed(1) + 'M';
            } else if (value >= 1000) {
              return (value / 1000).toFixed(1) + 'k';
            }
            return value;
          }
        }
      }
    );
  } else if (hasAxis0) {
    yAxis.push({ type: 'value', name: '数量', position: 'left' });
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
      boundaryGap: visibleSeries.some(s => s.type === 'bar'),
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
