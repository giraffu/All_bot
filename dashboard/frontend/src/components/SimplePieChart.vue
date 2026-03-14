<template>
  <div class="simple-pie-chart">
    <h3 class="chart-title" v-if="title">{{ title }}</h3>
    <div class="chart-container">
      <div class="svg-wrapper">
        <svg viewBox="-1 -1 2 2" style="transform: rotate(-90deg)">
          <path
            v-for="(slice, index) in slices"
            :key="index"
            :d="slice.path"
            :fill="slice.color"
            @mouseenter="activeSlice = index"
            @mouseleave="activeSlice = null"
            class="slice"
            :class="{ active: activeSlice === index }"
          >
            <title>{{ slice.name }}: {{ slice.value }} ({{ slice.percent }}%)</title>
          </path>
        </svg>
        <div class="center-hole" v-if="donut"></div>
      </div>
      <div class="legend">
        <div 
          v-for="(item, index) in processedData" 
          :key="index" 
          class="legend-item"
          @mouseenter="activeSlice = index"
          @mouseleave="activeSlice = null"
          :class="{ active: activeSlice === index }"
        >
          <span class="color-box" :style="{ backgroundColor: item.color }"></span>
          <span class="label">{{ item.name }}</span>
          <span class="value">{{ item.value }}</span>
          <span class="percent">{{ item.percent }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';

const props = defineProps({
  data: {
    type: Array, // [{ name: 'A', value: 10 }, ...]
    default: () => []
  },
  title: {
    type: String,
    default: ''
  },
  donut: {
    type: Boolean,
    default: false
  }
});

const activeSlice = ref(null);

const colors = [
  '#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', 
  '#13c2c2', '#eb2f96', '#2f54eb', '#a0d911', '#fa541c'
];

const total = computed(() => {
  return props.data.reduce((sum, item) => sum + (item.value || 0), 0);
});

const processedData = computed(() => {
  if (total.value === 0) return [];
  
  return props.data
    .filter(item => item.value > 0)
    .sort((a, b) => b.value - a.value)
    .map((item, index) => {
      const percent = ((item.value / total.value) * 100).toFixed(1);
      return {
        ...item,
        percent,
        color: colors[index % colors.length]
      };
    });
});

const slices = computed(() => {
  let cumulativePercent = 0;
  
  return processedData.value.map(item => {
    const startPercent = cumulativePercent;
    const endPercent = cumulativePercent + (item.value / total.value);
    cumulativePercent = endPercent;
    
    const startX = Math.cos(2 * Math.PI * startPercent);
    const startY = Math.sin(2 * Math.PI * startPercent);
    const endX = Math.cos(2 * Math.PI * endPercent);
    const endY = Math.sin(2 * Math.PI * endPercent);
    
    const largeArcFlag = (endPercent - startPercent) > 0.5 ? 1 : 0;
    
    const path = [
      `M 0 0`,
      `L ${startX} ${startY}`,
      `A 1 1 0 ${largeArcFlag} 1 ${endX} ${endY}`,
      `Z`
    ].join(' ');
    
    return {
      path,
      color: item.color,
      name: item.name,
      value: item.value,
      percent: item.percent
    };
  });
});
</script>

<style scoped>
.simple-pie-chart {
  background: white;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #f0f0f0;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #1f1f1f;
  text-align: center;
}

.chart-container {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 24px;
}

.svg-wrapper {
  width: 160px;
  height: 160px;
  flex-shrink: 0;
}

.slice {
  transition: opacity 0.2s;
  cursor: pointer;
}

.slice:hover, .slice.active {
  opacity: 0.8;
}

.legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
  flex: 1;
}

.legend-item {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: #595959;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}

.legend-item:hover, .legend-item.active {
  background-color: #f5f5f5;
}

.color-box {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 8px;
  flex-shrink: 0;
}

.label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-right: 8px;
}

.value {
  font-weight: 500;
  margin-right: 8px;
}

.percent {
  color: #8c8c8c;
  font-size: 12px;
  width: 40px;
  text-align: right;
}

@media (max-width: 640px) {
  .chart-container {
    flex-direction: column;
  }
  .legend {
    width: 100%;
  }
}
</style>
