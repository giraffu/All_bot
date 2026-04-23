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
    <div class="flex-1 min-h-0 relative">
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
import { fetchCumulativeTypeDistribution } from '../api/api';

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
    default: '累计生成类型分布'
  },
  donut: {
    type: Boolean,
    default: false
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
  'ltx_video': '高级图生视频',
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
  'ltx_video': '#722ed1',
  'unknown': '#bfbfbf'
};

const fetchData = async () => {
  loading.value = true;
  try {
    const data = await fetchCumulativeTypeDistribution(timeRange.value);
    chartData.value = data;
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
    name: typeMapping[key] || key,
    value: value,
    itemStyle: {
      color: typeColors[key] || undefined
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
