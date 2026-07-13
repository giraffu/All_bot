<template>
  <section class="dashboard-chart-frame flex flex-col">
    <header class="dashboard-chart-frame__header flex items-center justify-between gap-3">
      <h3 class="dashboard-chart-frame__title">{{ title }}</h3>
      <div class="dashboard-chart-frame__controls">
        <slot name="controls" />
      </div>
    </header>
    <div class="dashboard-chart-frame__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style scoped>
.dashboard-chart-frame {
  width: 100%;
  height: 100%;
  min-height: 300px;
  background: white;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #f0f0f0;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
}

.dashboard-chart-frame__header {
  flex-shrink: 0;
  margin-bottom: 16px;
}

.dashboard-chart-frame__title {
  margin: 0;
  color: #1f2937;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
}

.dashboard-chart-frame__controls {
  flex-shrink: 0;
}

.dashboard-chart-frame__body {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
}
</style>
