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
    card: 'hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.1)]',
    iconWrap:
      'bg-slate-500/50 border border-slate-400 text-cyan-400 group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]',
    text: 'text-slate-100',
  },
  indigo: {
    card: 'hover:border-indigo-500/30 hover:shadow-[0_8px_24px_rgba(99,102,241,0.1)]',
    iconWrap:
      'bg-slate-500/50 border border-slate-400 text-indigo-400 group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]',
    text: 'text-slate-100',
  },
  emerald: {
    card: 'hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)]',
    iconWrap:
      'bg-slate-500/50 border border-slate-400 text-emerald-400 group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]',
    text: 'text-slate-100',
  },
  amber: {
    card: 'hover:border-amber-500/30 hover:shadow-[0_8px_24px_rgba(245,158,11,0.1)]',
    iconWrap:
      'bg-slate-500/50 border border-slate-400 text-amber-400 group-hover:shadow-[0_0_12px_rgba(245,158,11,0.4)]',
    text: 'text-slate-100',
  },
  rose: {
    card: 'hover:border-rose-500/30 hover:shadow-[0_8px_24px_rgba(244,63,94,0.1)] relative overflow-hidden',
    iconWrap:
      'bg-rose-500/20 border border-rose-500/50 text-rose-400 group-hover:shadow-[0_0_15px_rgba(244,63,94,0.5)]',
    text: 'text-rose-100 drop-shadow-md',
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
        'rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] transition-all group',
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
          <p class="mb-1 text-xs md:text-sm text-slate-400">{{ item.title }}</p>
          <h3 :class="['text-lg md:text-xl font-bold drop-shadow-sm', item.valueClass ?? getAccentStyles(item.accent).text]">
            {{ item.value }}
          </h3>
        </div>
      </div>
    </a-card>
  </div>
</template>
