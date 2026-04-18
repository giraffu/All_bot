<template>
  <div class="chart-wrapper relative flex flex-col">
    <div class="flex justify-between items-center mb-4 px-2">
      <div class="font-bold text-base">{{ props.title }}</div>
      <div class="flex items-center gap-2" v-if="!props.showCumulativeOnly">
        <div class="flex gap-1">
          <a-tag 
            v-for="date in selectedDates.filter(d => d !== 'cumulative')" 
            :key="date" 
            closable 
            @close="removeDate(date)"
            :color="getDateColor(date)"
          >
            {{ formatDate(date) }}
          </a-tag>
        </div>
        <a-date-picker 
          v-if="selectedDates.filter(d => d !== 'cumulative').length < 3"
          :value="null" 
          :allowClear="false"
          placeholder="添加对比日期"
          @change="handleAddDate"
          size="small"
          style="width: 110px"
          :disabled-date="disabledDate"
        />
        <a-button 
          size="small" 
          :type="selectedDates.includes('cumulative') ? 'primary' : 'default'"
          @click="toggleCumulative"
        >
          累计
        </a-button>
      </div>
      <div class="flex items-center gap-2" v-else>
        <a-radio-group 
          v-model:value="localTimeRange"
          button-style="solid"
          size="small"
          @change="fetchData"
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
    </div>
    <div class="flex-1 min-h-0">
      <v-chart class="chart" :option="option" autoresize :loading="loading" />
    </div>
  </div>
</template>

<script setup>
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed, ref, onMounted, watch } from 'vue';
import { fetchFinanceHourlyStats, fetchCumulativeFinanceHourlyStats } from '../api/api';
import dayjs from 'dayjs';

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: '分时统计'
  },
  metric: {
    type: String,
    default: 'credits' // 'credits' or 'disciples'
  },
  colors: {
    type: Array,
    default: () => ['#1890ff', '#52c41a', '#faad14']
  },
  timeRange: {
    type: Number,
    default: 7
  },
  timeRangeOptions: {
    type: Array,
    default: () => [
      { label: '最近 7 天', value: 7 },
      { label: '最近 2 周', value: 14 },
      { label: '最近 1 个月', value: 30 },
      { label: '最近 2 个月', value: 60 },
      { label: '最近 3 个月', value: 90 },
      { label: '最近半年', value: 180 },
      { label: '最近 1 年', value: 365 }
    ]
  },
  showCumulativeOnly: {
    type: Boolean,
    default: false
  }
});

const localTimeRange = ref(props.timeRange);
const loading = ref(false);
// Store dates as YYYY-MM-DD strings
const selectedDates = ref(props.showCumulativeOnly ? ['cumulative'] : [dayjs().format('YYYY-MM-DD')]);
const chartDataMap = ref({}); // { 'YYYY-MM-DD': { '00': 10, ... }, 'cumulative': { '00': 50, ... } }

const getDateColor = (date) => {
  if (date === 'cumulative') return '#cf1322'; // distinct color for cumulative line
  const index = selectedDates.value.indexOf(date);
  return index !== -1 ? props.colors[index % props.colors.length] : '#ccc';
};

const formatDate = (dateStr) => {
  if (dateStr === 'cumulative') return `累计 (${localTimeRange.value}天)`;
  return dayjs(dateStr).format('MM-DD');
};

const disabledDate = (current) => {
  // Can not select future days
  return current && current > dayjs().endOf('day');
};

const fetchData = async () => {
  if (selectedDates.value.length === 0) {
    chartDataMap.value = {};
    return;
  }
  
  loading.value = true;
  try {
    const promises = selectedDates.value.map(async (dateStr) => {
      let rawData;
      if (dateStr === 'cumulative') {
        rawData = await fetchCumulativeFinanceHourlyStats(localTimeRange.value);
      } else {
        rawData = await fetchFinanceHourlyStats(dateStr);
      }
      
      const parsedData = {};
      for (const [hour, stats] of Object.entries(rawData)) {
        if (props.metric === 'credits') {
          parsedData[hour] = stats.recharged_credits || 0;
        } else if (props.metric === 'disciples') {
          parsedData[hour] = (stats.inner_disciples || 0) + (stats.core_disciples || 0) + (stats.true_disciples || 0);
        }
      }
      return { date: dateStr, data: parsedData };
    });
    
    const results = await Promise.all(promises);
    const newMap = {};
    results.forEach(({ date, data }) => {
      newMap[date] = data;
    });
    chartDataMap.value = newMap;
  } catch (error) {
    console.error('Failed to fetch hourly stats:', error);
  } finally {
    loading.value = false;
  }
};

const handleAddDate = (date) => {
  if (!date) return;
  const dateStr = date.format('YYYY-MM-DD');
  if (!selectedDates.value.includes(dateStr)) {
    selectedDates.value.push(dateStr);
    fetchData();
  }
};

const toggleCumulative = () => {
  if (selectedDates.value.includes('cumulative')) {
    removeDate('cumulative');
  } else {
    selectedDates.value.push('cumulative');
    fetchData();
  }
};

const removeDate = (dateStr) => {
  selectedDates.value = selectedDates.value.filter(d => d !== dateStr);
  // Remove data from map locally
  const newMap = { ...chartDataMap.value };
  delete newMap[dateStr];
  chartDataMap.value = newMap;
};

onMounted(() => {
  fetchData();
});

const option = computed(() => {
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'));
  
  const series = selectedDates.value.map((dateStr, index) => {
    const dataObj = chartDataMap.value[dateStr] || {};
    const data = hours.map(h => dataObj[h] || 0);
    
    if (dateStr === 'cumulative') {
      return {
        name: formatDate(dateStr),
        type: 'bar',
        yAxisIndex: props.showCumulativeOnly ? 0 : 1,
        data: data,
        itemStyle: {
          color: props.showCumulativeOnly ? props.colors[0] : '#cf1322',
          borderRadius: [4, 4, 0, 0]
        },
        emphasis: {
          focus: 'series'
        },
        barMaxWidth: 20
      };
    }
    
    return {
      name: formatDate(dateStr),
      type: 'bar',
      yAxisIndex: 0,
      data: data,
      itemStyle: {
        color: props.colors[index % props.colors.length],
        borderRadius: [4, 4, 0, 0]
      },
      emphasis: {
        focus: 'series'
      },
      barMaxWidth: 20
    };
  });

  return {
    // Remove title from chart as we have custom header
    // title: {
    //   text: props.title,
    //   left: 'center',
    //   textStyle: { fontSize: 16, fontWeight: '600' }
    // },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: selectedDates.value.map(d => formatDate(d)),
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      top: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: hours.map(h => `${h}时`),
      axisLabel: {
        interval: 1, // Show every 2nd label
      }
    },
    yAxis: [
      {
        type: 'value',
        name: props.showCumulativeOnly ? '累计新增' : '单日新增',
        position: 'left',
        splitLine: {
          lineStyle: {
            type: 'dashed'
          }
        },
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
      },
      {
        type: 'value',
        name: '累计新增',
        position: 'right',
        show: !props.showCumulativeOnly,
        splitLine: {
          show: false
        },
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
    ],
    series: series
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
