<template>
  <DistributionBarChartBase
    :title="title"
    :data="data"
    :categories="categories"
    x-axis-name="修为"
    tooltip-formatter="{b}: {c} 人"
    color="#faad14"
  />
</template>

<script setup lang="ts">
import DistributionBarChartBase from './DistributionBarChartBase.vue';

withDefaults(defineProps<{
  title?: string;
  data?: Record<string, number>;
}>(), {
  title: '用户修为分布',
  data: () => ({})
});

const categories = ['凡人', '练气期', '筑基期', '金丹期', '元婴期'];
</script>
