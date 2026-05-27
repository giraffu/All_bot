<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'

export type ProfileMetricCardItem = {
  key: string
  title: string
  value: string | number
  accent: 'cyan' | 'indigo' | 'emerald' | 'amber' | 'rose'
  icon?: Component
  iconText?: string
  colSpanClass?: string
  valueClass?: string
}

const props = defineProps<{
  items: ProfileMetricCardItem[]
  iconSize?: number
}>()

const iconSize = computed(() => props.iconSize ?? 24)

const ACCENT_STYLES: Record<
  ProfileMetricCardItem['accent'],
  {
    card: string
    iconWrap: string
    text: string
  }
> = {
  cyan: {
    card: 'metric-card--cyan',
    iconWrap: 'metric-icon metric-icon--cyan',
    text: 'metric-value',
  },
  indigo: {
    card: 'metric-card--indigo',
    iconWrap: 'metric-icon metric-icon--indigo',
    text: 'metric-value',
  },
  emerald: {
    card: 'metric-card--emerald',
    iconWrap: 'metric-icon metric-icon--emerald',
    text: 'metric-value',
  },
  amber: {
    card: 'metric-card--amber',
    iconWrap: 'metric-icon metric-icon--amber',
    text: 'metric-value',
  },
  rose: {
    card: 'metric-card--rose relative overflow-hidden',
    iconWrap: 'metric-icon metric-icon--rose',
    text: 'metric-value metric-value--rose',
  },
}

const getAccentStyles = (accent: ProfileMetricCardItem['accent']) => ACCENT_STYLES[accent]
</script>

<template>
  <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
    <a-card
      v-for="item in items"
      :key="item.key"
      hoverable
      :class="[
        item.colSpanClass,
        'metric-card rounded-xl backdrop-blur-md transition-all group',
        getAccentStyles(item.accent).card,
      ]"
    >
      <div
        v-if="item.accent === 'rose'"
        class="absolute top-0 right-0 -mr-2 -mt-2 h-16 w-16 rounded-full bg-gradient-to-br from-rose-400 to-orange-500 opacity-20 blur-xl"
      />
      <div class="flex items-center flex-col md:flex-row text-center md:text-left relative z-10">
        <div
          :class="[
            'mb-2 md:mb-0 md:mr-4 flex h-10 w-10 md:h-12 md:w-12 items-center justify-center rounded-full transition-transform group-hover:scale-110',
            getAccentStyles(item.accent).iconWrap,
          ]"
        >
          <component
            :is="item.icon"
            v-if="item.icon"
            :size="iconSize"
          />
          <span v-else class="text-xl font-bold">{{ item.iconText ?? '$' }}</span>
        </div>
        <div>
          <p class="metric-title mb-1 text-xs md:text-sm">{{ item.title }}</p>
          <h3 :class="['text-lg md:text-xl font-bold drop-shadow-sm', item.valueClass ?? getAccentStyles(item.accent).text]">
            {{ item.value }}
          </h3>
        </div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.metric-card {
  background: var(--theme-card-bg);
  border: 1px solid var(--theme-border);
  box-shadow: var(--theme-shadow);
}

.metric-card--cyan:hover {
  border-color: rgba(34, 211, 238, 0.35);
  box-shadow: 0 8px 24px rgba(56, 189, 248, 0.12);
}

.metric-card--indigo:hover {
  border-color: rgba(129, 140, 248, 0.35);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.12);
}

.metric-card--emerald:hover {
  border-color: rgba(16, 185, 129, 0.35);
  box-shadow: 0 8px 24px rgba(16, 185, 129, 0.12);
}

.metric-card--amber:hover {
  border-color: rgba(245, 158, 11, 0.35);
  box-shadow: 0 8px 24px rgba(245, 158, 11, 0.12);
}

.metric-card--rose:hover {
  border-color: rgba(244, 63, 94, 0.35);
  box-shadow: 0 8px 24px rgba(244, 63, 94, 0.12);
}

.metric-icon {
  background: var(--theme-pill-bg);
  border: 1px solid var(--theme-border);
}

.metric-icon--cyan {
  color: #06b6d4;
}

.metric-icon--indigo {
  color: #6366f1;
}

.metric-icon--emerald {
  color: #10b981;
}

.metric-icon--amber {
  color: #f59e0b;
}

.metric-icon--rose {
  background: rgba(244, 63, 94, 0.12);
  border-color: rgba(244, 63, 94, 0.28);
  color: #f43f5e;
}

.metric-title {
  color: var(--theme-text-secondary);
}

.metric-value {
  color: var(--theme-text-primary);
}

.metric-value--rose {
  color: #e11d48;
}
</style>
