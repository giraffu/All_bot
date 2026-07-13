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
  <StickyHeaderSection class-name="gallery-filters-sticky -mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
    <template v-if="isMobile">
      <div class="gallery-filter-mobile">
        <SegmentedTabsRail
          :items="taskTypeTabs"
          :selected-id="taskType"
          container-class="gallery-filter-mobile__tabs w-full shrink-0"
          content-class="gallery-filter-mobile__tabs-content flex gap-1 bg-[var(--theme-pill-bg)] p-0.5 rounded-xl border border-[var(--theme-border)]"
          button-class="gallery-filter-mobile__tab px-2.5 py-1 rounded-lg transition-all font-semibold text-[12px] leading-5 whitespace-nowrap shrink-0"
          active-class="bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]"
          inactive-class="text-[var(--theme-text-secondary)] border border-transparent hover:text-[var(--theme-tab-hover-text)]"
          @select="emit('taskTypeChange', $event)"
        />

        <OverflowScrollRail
          container-class="gallery-filter-mobile__chips w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] px-1.5 py-1 shadow-[0_6px_16px_rgba(15,23,42,0.1)]"
          content-class="flex items-center gap-1.5"
        >
          <button
            v-for="time in timeOptions"
            :key="time.key"
            class="gallery-filter-mobile__chip"
            :class="timeRange === time.key ? 'gallery-filter-mobile__chip--active' : 'gallery-filter-mobile__chip--muted'"
            @click="emit('timeRangeChange', time.key)"
          >
            {{ $t(time.labelKey) }}
          </button>

          <span class="gallery-filter-mobile__divider" aria-hidden="true"></span>

          <button
            v-for="sort in sortOptions"
            :key="sort.key"
            class="gallery-filter-mobile__chip"
            :class="sortBy === sort.key ? 'gallery-filter-mobile__chip--active' : 'gallery-filter-mobile__chip--muted'"
            @click="emit('sortChange', sort.key)"
          >
            <component :is="sort.icon" :size="12" class="mr-1 shrink-0" />
            {{ $t(sort.labelKey) }}
          </button>

          <template v-if="hasAddonSubfilters">
            <span class="gallery-filter-mobile__divider" aria-hidden="true"></span>

            <button
              class="gallery-filter-mobile__chip"
              :class="loraModel === 'all' ? 'gallery-filter-mobile__chip--addon-active' : 'gallery-filter-mobile__chip--muted'"
              @click="emit('loraModelChange', 'all')"
            >
              {{ $t('gallery.filters.all') }}
            </button>
            <button
              class="gallery-filter-mobile__chip"
              :class="loraModel === loraModelNoneValue ? 'gallery-filter-mobile__chip--addon-active' : 'gallery-filter-mobile__chip--muted'"
              @click="emit('loraModelChange', loraModelNoneValue)"
            >
              {{ $t('gallery.no_addon') }}
            </button>
            <button
              v-for="lora in currentLoraModels"
              :key="lora.id"
              class="gallery-filter-mobile__chip"
              :class="loraModel === lora.id ? 'gallery-filter-mobile__chip--addon-active' : 'gallery-filter-mobile__chip--muted'"
              @click="emit('loraModelChange', lora.id)"
            >
              {{ lora.name }}
            </button>
          </template>
        </OverflowScrollRail>

        <HeaderPaginationBar
          v-if="totalPages > 1"
          wrapper-class="gallery-filter-mobile__pager-wrap"
          inner-class="gallery-filter-mobile__pager"
          :current-page="currentPage"
          :total-pages="totalPages"
          :disabled="loading"
          :compact="true"
          :show-jump="true"
          :minimal="true"
          @change="emit('pageChange', $event)"
        />
      </div>
    </template>

    <template v-else>
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
      :show-jump="true"
      @change="emit('pageChange', $event)"
    />
    </template>
  </StickyHeaderSection>
</template>

<style scoped>
.gallery-filter-mobile {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

:deep(.gallery-filter-mobile__tabs),
:deep(.gallery-filter-mobile__chips) {
  min-height: 2.1rem;
}

.gallery-filter-mobile__chip {
  height: 1.75rem;
  padding: 0 0.6rem;
  border-radius: 0.6rem;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-text-secondary);
  font-size: 0.75rem;
  font-weight: 650;
  line-height: 1;
  white-space: nowrap;
  flex-shrink: 0;
  transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.gallery-filter-mobile__chip--muted {
  border-color: var(--theme-border);
  background: var(--theme-pill-bg);
}

.gallery-filter-mobile__chip--active {
  border-color: var(--theme-tab-active-border);
  background: var(--theme-tab-active-bg);
  color: var(--theme-tab-active-text);
  box-shadow: var(--theme-tab-active-shadow);
}

.gallery-filter-mobile__chip--addon-active {
  border-color: rgb(236 72 153 / 0.52);
  background: rgb(236 72 153 / 0.16);
  color: #ec4899;
  box-shadow: 0 0 10px rgb(236 72 153 / 0.12);
}

.gallery-filter-mobile__divider {
  width: 1px;
  height: 1.25rem;
  margin: 0 0.125rem;
  background: var(--theme-border);
  flex-shrink: 0;
}

:deep(.gallery-filter-mobile__pager-wrap) {
  display: flex;
  justify-content: center;
}

:deep(.gallery-filter-mobile__pager) {
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
  border-radius: 0.8rem;
  padding: 0.2rem 0.25rem;
  box-shadow: 0 6px 16px rgb(15 23 42 / 0.1);
}

.gallery-filter-mobile :deep(.scroll-button) {
  width: 1.85rem;
  height: 1.85rem;
}

.gallery-filter-mobile :deep(.scroll-fade-left) {
  width: 2.25rem;
}

.gallery-filter-mobile :deep(.scroll-fade-right) {
  width: 2.5rem;
}

@media (max-width: 767px) {
  :deep(.gallery-filters-sticky) {
    padding-top: 0.5rem;
    gap: 0.375rem;
    margin-bottom: 0.5rem;
  }
}
</style>
