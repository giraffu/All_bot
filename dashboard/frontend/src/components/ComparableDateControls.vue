<template>
  <div class="flex items-center gap-2">
    <div class="flex gap-1">
      <a-tag
        v-for="date in regularDates"
        :key="date"
        closable
        :color="getDateColor(date)"
        @close="emit('removeDate', date)"
      >
        {{ formatDate(date) }}
      </a-tag>
    </div>
    <a-date-picker
      v-if="regularDates.length < maxDates"
      :value="null"
      :allow-clear="false"
      :placeholder="placeholder"
      size="small"
      :style="{ width: pickerWidth }"
      :disabled-date="disabledDate"
      @change="emit('addDate', $event)"
    />
    <a-button
      v-if="showCumulativeToggle"
      size="small"
      :type="cumulativeSelected ? 'primary' : 'default'"
      @click="emit('toggleCumulative')"
    >
      累计
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Dayjs } from 'dayjs'
import { CUMULATIVE_DATE_KEY } from '../composables/useComparableDates'

const props = withDefaults(defineProps<{
  selectedDates: string[]
  formatDate: (dateKey: string) => string
  getDateColor: (dateKey: string) => string
  disabledDate: (current: Dayjs) => boolean
  maxDates?: number
  placeholder?: string
  pickerWidth?: string
  showCumulativeToggle?: boolean
  cumulativeSelected?: boolean
}>(), {
  maxDates: 3,
  placeholder: '添加对比日期',
  pickerWidth: '110px',
  showCumulativeToggle: false,
  cumulativeSelected: false,
})

const emit = defineEmits<{
  addDate: [date: Dayjs | null]
  removeDate: [dateKey: string]
  toggleCumulative: []
}>()

const regularDates = computed(() => (
  props.selectedDates.filter(date => date !== CUMULATIVE_DATE_KEY)
))
</script>
