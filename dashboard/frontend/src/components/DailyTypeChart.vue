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
            color="blue"
          >
            {{ formatDate(date) }}
          </a-tag>
        </div>
        <a-date-picker 
          v-if="selectedDates.length < 3"
          :value="null" 
          :allowClear="false"
          placeholder="添加对比"
          @change="handleAddDate"
          size="small"
          style="width: 100px"
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
import { PieChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent
} from 'echarts/components';
import VChart from 'vue-echarts';
import { computed, ref, onMounted } from 'vue';
import { fetchTypeDistribution } from '../api/api';
import dayjs from 'dayjs';

use([
  CanvasRenderer,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent
]);

const props = defineProps({
  title: {
    type: String,
    default: '生成类型分布'
  },
  donut: {
    type: Boolean,
    default: false
  }
});

const loading = ref(false);
const selectedDates = ref([dayjs().format('YYYY-MM-DD')]);
const chartDataMap = ref({}); // { 'YYYY-MM-DD': { 'type': count, ... } }

const typeMapping = {
  'undress': '快速脱衣',
  'face_swap': '快速换脸',
  'faceswap_step1': '快速换脸',
  'faceswap_step2': '快速换脸',
  'random_faceswap': '随机换脸',
  'face_show': '动图露奶',
  'face_tongue': '动图吐舌',
  'fuck': '动图做爱',
  'penetration': '快速抽插',
  'penetration_step1': '快速抽插',
  'penetration_step2': '快速抽插',
  'perfect_video_insert': '动图传教士',
  'doggy_style': '动图后入',
  'blowjob': '口交黑人',
  'masturbation': '快速自慰',
  'image': '自由P图',
  'edit': '自由P图',
  'video': '视频生成',
  'video_pro': '专业视频',
  'custom_video': '自定义视频',
  'template_contribute': '模板共建',
  'undress_tongue': '脱衣吐舌',
  'closeup_blowjob': '特写口交',
  'text_to_image': '文生图',
  'i2i_pro': '幻想换脸',
  'video_lora': '图生视频(附加模型)',
  'unknown': '未知类型'
};

const typeColors = {
  'undress': '#ff7875',
  'face_swap': '#40a9ff',
  'faceswap_step1': '#40a9ff',
  'faceswap_step2': '#40a9ff',
  'random_faceswap': '#096dd9',
  'face_show': '#9254de',
  'face_tongue': '#722ed1',
  'fuck': '#eb2f96',
  'penetration': '#f759ab',
  'penetration_step1': '#f759ab',
  'penetration_step2': '#f759ab',
  'perfect_video_insert': '#faad14',
  'doggy_style': '#d48806',
  'blowjob': '#fa541c',
  'masturbation': '#ffc069',
  'image': '#ffd666',
  'edit': '#ffd666',
  'video': '#36cfc9',
  'video_pro': '#597ef7',
  'custom_video': '#13c2c2',
  'video_lora': '#2f54eb',
  'template_contribute': '#8c8c8c',
  'undress_tongue': '#bae637',
  'closeup_blowjob': '#ff4d4f',
  'text_to_image': '#52c41a',
  'i2i_pro': '#ff85c0',
  'unknown': '#bfbfbf'
};

const formatDate = (dateStr) => {
  return dayjs(dateStr).format('MM-DD');
};

const disabledDate = (current) => {
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
      const data = await fetchTypeDistribution(dateStr);
      return { date: dateStr, data };
    });
    
    const results = await Promise.all(promises);
    const newMap = {};
    results.forEach(({ date, data }) => {
      newMap[date] = data;
    });
    chartDataMap.value = newMap;
  } catch (error) {
    console.error('Failed to fetch type distribution:', error);
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
  const newMap = { ...chartDataMap.value };
  delete newMap[dateStr];
  chartDataMap.value = newMap;
};

onMounted(() => {
  fetchData();
});

const getTransformData = (dateStr) => {
  const data = chartDataMap.value[dateStr];
  if (!data) return [];
  return Object.entries(data).map(([key, value]) => ({
    name: typeMapping[key] || key,
    value: value,
    itemStyle: {
      color: typeColors[key] || undefined
    }
  }));
};

const option = computed(() => {
  const count = selectedDates.value.length;
  if (count === 0) return {};

  const titles = [];
  const series = [];
  
  // Layout configuration based on count
  let centers = [];
  let radius = props.donut ? ['30%', '50%'] : '50%';
  
  if (count === 1) {
    centers = [['60%', '50%']];
    radius = props.donut ? ['40%', '70%'] : '60%';
  } else if (count === 2) {
    centers = [['40%', '50%'], ['80%', '50%']];
    radius = props.donut ? ['30%', '50%'] : '45%';
  } else if (count === 3) {
    centers = [['30%', '50%'], ['60%', '50%'], ['90%', '50%']];
    radius = props.donut ? ['25%', '40%'] : '35%';
  }

  selectedDates.value.forEach((dateStr, index) => {
    // Title for each pie
    titles.push({
      text: formatDate(dateStr),
      left: centers[index][0],
      top: '85%',
      textAlign: 'center',
      textStyle: {
        fontSize: 14,
        fontWeight: 'normal'
      }
    });

    // Series for each pie
    series.push({
      name: formatDate(dateStr),
      type: 'pie',
      radius: radius,
      center: centers[index],
      data: getTransformData(dateStr),
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
    });
  });

  return {
    title: titles,
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      top: 'middle',
      left: 'left',
      type: 'scroll'
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
