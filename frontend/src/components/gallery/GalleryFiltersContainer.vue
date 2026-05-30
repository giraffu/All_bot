<script setup lang="ts">
import { Clock, Flame, Heart } from 'lucide-vue-next'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

interface TabItem {
  id: string
  name: string
}

interface LoraModelOption {
  id: string
  name: string
}

const props = defineProps<{
  taskTypeTabs: TabItem[]
  taskType: string
  timeRange: string
  sortBy: string
  hasAddonSubfilters: boolean
  currentLoraModels: LoraModelOption[]
  loraModel: string
  loraModelNoneValue: string
  currentPage: number
  totalPages: number
  isMobile: boolean
  loading: boolean
}>()

warnIfPropsExceedBudget('GalleryFiltersContainer', Object.keys(props).length)

const emit = defineEmits<{
  taskTypeChange: [value: string]
  timeRangeChange: [value: string]
  sortChange: [value: string]
  loraModelChange: [value: string]
  pageChange: [value: number]
}>()

const timeOptions = [
  { key: 'all', labelKey: 'gallery.filters.all' },
  { key: 'today', labelKey: 'gallery.filters.today' },
  { key: 'week', labelKey: 'gallery.filters.this_week' },
  { key: 'month', labelKey: 'gallery.filters.this_month' },
]

const sortOptions = [
  { key: 'latest', labelKey: 'gallery.filters.latest', icon: Clock },
  { key: 'likes', labelKey: 'gallery.filters.most_liked', icon: Heart },
  { key: 'applied', labelKey: 'gallery.filters.most_used', icon: Flame },
]
</script>

<template>
  <StickyHeaderSection class-name="-mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
    <div class="flex flex-col xl:flex-row justify-between xl:items-center gap-4">
      <SegmentedTabsRail
        :items="taskTypeTabs"
        :selected-id="taskType"
        container-class="w-full xl:w-auto shrink-0"
        content-class="flex gap-1 bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)]"
        active-class="bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]"
        inactive-class="text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]"
        @select="emit('taskTypeChange', $event)"
      />

      <OverflowScrollRail
        container-class="w-full xl:w-auto shrink-0 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] px-2 py-2 shadow-[0_6px_18px_rgba(15,23,42,0.12)]"
        content-class="flex items-center gap-3"
      >
        <div class="flex bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)] shrink-0">
          <button
            v-for="time in timeOptions"
            :key="time.key"
            class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
            :class="timeRange === time.key ? 'bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]' : 'text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]'"
            @click="emit('timeRangeChange', time.key)"
          >
            {{ $t(time.labelKey) }}
          </button>
        </div>

        <div class="flex bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)] shrink-0">
          <button
            v-for="sort in sortOptions"
            :key="sort.key"
            class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm flex items-center whitespace-nowrap shrink-0"
            :class="sortBy === sort.key ? 'bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]' : 'text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]'"
            @click="emit('sortChange', sort.key)"
          >
            <component :is="sort.icon" :size="14" class="mr-1.5 hidden sm:block" />
            {{ $t(sort.labelKey) }}
          </button>
        </div>
      </OverflowScrollRail>
    </div>

    <OverflowScrollRail
      v-if="hasAddonSubfilters"
      container-class="w-full shrink-0 px-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] py-2 shadow-[0_6px_18px_rgba(15,23,42,0.12)]"
      content-class="flex items-center gap-2"
    >
      <span class="text-xs sm:text-sm text-[var(--theme-text-secondary)] whitespace-nowrap shrink-0">
        {{ $t('gallery.choose_addon') }}
      </span>
      <div class="flex gap-2 shrink-0">
        <button
          class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
          :class="loraModel === 'all' ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
          @click="emit('loraModelChange', 'all')"
        >
          {{ $t('gallery.filters.all') }}
        </button>
        <button
          class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
          :class="loraModel === loraModelNoneValue ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
          @click="emit('loraModelChange', loraModelNoneValue)"
        >
          {{ $t('gallery.no_addon') }}
        </button>
        <button
          v-for="lora in currentLoraModels"
          :key="lora.id"
          class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
          :class="loraModel === lora.id ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
          @click="emit('loraModelChange', lora.id)"
        >
          {{ lora.name }}
        </button>
      </div>
    </OverflowScrollRail>

    <HeaderPaginationBar
      wrapper-class="-mt-1 flex justify-center"
      :current-page="currentPage"
      :total-pages="totalPages"
      :disabled="loading"
      :compact="isMobile"
      @change="emit('pageChange', $event)"
    />
  </StickyHeaderSection>
</template>
