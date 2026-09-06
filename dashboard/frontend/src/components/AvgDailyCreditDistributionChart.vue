<template>
  <DistributionBarChartBase
    :title="title"
    :data="data"
    :categories="categories"
    x-axis-name="积分/天"
    tooltip-formatter="{b} 积分/天: {c} 人"
    color="#f5222d"
  />
</template>

<script setup lang="ts">
import DistributionBarChartBase from './DistributionBarChartBase.vue';

withDefaults(defineProps<{
  title?: string;
  data?: Record<string, number>;
}>(), {
  title: '用户日均积分消耗分布',
  data: () => ({})
});

const categories = ['0', '0-1', '1-5', '5-10', '10-20', '20-50', '50+'];
</script>
