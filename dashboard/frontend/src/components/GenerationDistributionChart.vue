<template>
  <DistributionBarChartBase
    :title="title"
    :data="data"
    :categories="categories"
    x-axis-name="生成量"
    tooltip-formatter="{b} 生成量: {c} 人"
    color="#722ed1"
    :axis-label-rotation="30"
  />
</template>

<script setup lang="ts">
import DistributionBarChartBase from './DistributionBarChartBase.vue';

withDefaults(defineProps<{
  title?: string;
  data?: Record<string, number>;
}>(), {
  title: '用户生成量分布',
  data: () => ({})
});

const categories = [
  '0', '1', '2', '3', '4', '5', '6-10', '11-20', '21-50', '51-100',
  '101-200', '201-500', '501-1000', '1000+'
];
</script>
