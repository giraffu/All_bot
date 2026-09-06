<template>
  <DistributionBarChartBase
    :title="title"
    :data="data"
    :categories="categories"
    x-axis-name="积分"
    tooltip-formatter="{b} 积分: {c} 人"
    color="#52c41a"
    :axis-label-rotation="30"
  />
</template>

<script setup lang="ts">
import DistributionBarChartBase from './DistributionBarChartBase.vue';

withDefaults(defineProps<{
  title?: string;
  data?: Record<string, number>;
}>(), {
  title: '用户持有积分分布',
  data: () => ({})
});

const categories = ['0', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001-5000', '5000+'];
</script>
