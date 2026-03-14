<template>
  <div class="chart-wrapper relative flex flex-col">
    <div class="flex justify-between items-center mb-4 px-2">
      <div class="font-bold text-base">{{ props.title }}</div>
      <div class="flex items-center gap-2">
        <div class="flex gap-1">
          <a-tag 
            v-for="date in selectedDates" 
            :key="date" 
            closable 
            @close="removeDate(date)"
            :color="getDateColor(date)"
          >
            {{ formatDate(date) }}
          </a-tag>
        </div>
        <a-date-picker 
          v-if="selectedDates.length < 3"
          :value="null" 
          :allowClear="false"
          placeholder="添加对比日期"
          @change="handleAddDate"
          size="small"
          style="width: 110px"
          :disabled-date="disabledDate"
        />
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
import { BarChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed, ref, onMounted, watch } from 'vue';
import { fetchHourlyStats } from '../api/api';
import dayjs from 'dayjs';

use([
  CanvasRenderer,
  BarChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: '分时生成量'
  }
});

const loading = ref(false);
// Store dates as YYYY-MM-DD strings
const selectedDates = ref([dayjs().format('YYYY-MM-DD')]);
const chartDataMap = ref({}); // { 'YYYY-MM-DD': { '00': 10, ... } }

const colors = ['#1890ff', '#52c41a', '#faad14'];

const getDateColor = (date) => {
  const index = selectedDates.value.indexOf(date);
  return index !== -1 ? colors[index] : '#ccc';
};

const formatDate = (dateStr) => {
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
      // If we already have data for this date and it's not today (historical data doesn't change), use cached
      // But for simplicity and to ensure fresh data for today, we'll just fetch all for now, 
      // or maybe optimize later. The API is fast enough.
      const data = await fetchHourlyStats(dateStr);
      return { date: dateStr, data };
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
    
    return {
      name: formatDate(dateStr),
      type: 'bar',
      data: data,
      itemStyle: {
        color: colors[index],
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
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: hours.map(h => `${h}时`),
      axisLabel: {
        interval: 1 // Show every 2nd label
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
