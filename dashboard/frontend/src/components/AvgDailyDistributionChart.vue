<template>
  <DistributionBarChartBase
    :title="title"
    :data="data"
    :categories="categories"
    x-axis-name="次/天"
    tooltip-formatter="{b} 次/天: {c} 人"
    color="#13c2c2"
  />
</template>

<script setup lang="ts">
import DistributionBarChartBase from './DistributionBarChartBase.vue';

withDefaults(defineProps<{
  title?: string;
  data?: Record<string, number>;
}>(), {
  title: '用户日均生成量分布',
  data: () => ({})
});

const categories = ['0', '0-1', '1-3', '3-5', '5-10', '10-20', '20+'];
</script>
