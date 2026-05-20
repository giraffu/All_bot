<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, useTemplateRef, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    containerClass?: string
    contentClass?: string
    buttonOffsetClass?: string
    disabled?: boolean
    scrollStep?: number
  }>(),
  {
    containerClass: '',
    contentClass: '',
    buttonOffsetClass: '',
    disabled: false,
    scrollStep: 18,
  },
)

const railRef = useTemplateRef<HTMLDivElement>('railRef')
const showLeftButton = ref(false)
const showRightButton = ref(false)
const isScrollable = computed(
  () => showLeftButton.value || showRightButton.value,
)

let resizeObserver: ResizeObserver | null = null
let contentResizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null
let rafId: number | null = null
let activeDirection: 'left' | 'right' | null = null
let refreshTimers: number[] = []

const scheduleRefresh = () => {
  if (typeof window === 'undefined') return

  refreshTimers.forEach((timer) => window.clearTimeout(timer))
  refreshTimers = []

  requestAnimationFrame(updateButtons)

  refreshTimers.push(window.setTimeout(updateButtons, 0))
  refreshTimers.push(window.setTimeout(updateButtons, 120))
  refreshTimers.push(window.setTimeout(updateButtons, 320))
}

const updateButtons = () => {
  const el = railRef.value
  if (!el || props.disabled) {
    showLeftButton.value = false
    showRightButton.value = false
    return
  }

  const maxScrollLeft = Math.max(el.scrollWidth - el.clientWidth, 0)
  const scrollLeft = el.scrollLeft
  const tolerance = 8

  showLeftButton.value = scrollLeft > tolerance
  showRightButton.value = maxScrollLeft - scrollLeft > tolerance
}

const stopScroll = () => {
  activeDirection = null
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

const tickScroll = () => {
  const el = railRef.value
  if (!el || !activeDirection) {
    stopScroll()
    return
  }

  el.scrollLeft += activeDirection === 'right' ? props.scrollStep : -props.scrollStep
  updateButtons()

  if (
    (activeDirection === 'right' && !showRightButton.value) ||
    (activeDirection === 'left' && !showLeftButton.value)
  ) {
    stopScroll()
    return
  }

  rafId = requestAnimationFrame(tickScroll)
}

const startScroll = (direction: 'left' | 'right') => {
  if (props.disabled) return
  activeDirection = direction
  if (rafId === null) {
    rafId = requestAnimationFrame(tickScroll)
  }
}

const nudgeScroll = (direction: 'left' | 'right') => {
  const el = railRef.value
  if (!el) return
  el.scrollTo({
    left: el.scrollLeft + (direction === 'right' ? 140 : -140),
    behavior: 'smooth',
  })
  requestAnimationFrame(updateButtons)
}

onMounted(async () => {
  await nextTick()
  scheduleRefresh()

  if (railRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      scheduleRefresh()
    })
    resizeObserver.observe(railRef.value)

    const contentEl = railRef.value.firstElementChild
    if (contentEl instanceof HTMLElement) {
      contentResizeObserver = new ResizeObserver(() => {
        scheduleRefresh()
      })
      contentResizeObserver.observe(contentEl)
    }
  }

  if (railRef.value && typeof MutationObserver !== 'undefined') {
    mutationObserver = new MutationObserver(() => {
      scheduleRefresh()
    })
    mutationObserver.observe(railRef.value, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    })
  }

  window.addEventListener('resize', scheduleRefresh)
})

watch(
  () => props.disabled,
  async () => {
    await nextTick()
    scheduleRefresh()
  },
)

onUpdated(() => {
  scheduleRefresh()
})

onBeforeUnmount(() => {
  stopScroll()
  resizeObserver?.disconnect()
  contentResizeObserver?.disconnect()
  mutationObserver?.disconnect()
  refreshTimers.forEach((timer) => window.clearTimeout(timer))
  window.removeEventListener('resize', scheduleRefresh)
})
</script>

<template>
  <div class="relative min-w-0">
    <div
      ref="railRef"
      class="overflow-x-auto scrollbar-hide"
      :class="containerClass"
      @scroll="updateButtons"
    >
      <div class="min-w-max" :class="contentClass">
        <slot />
      </div>
    </div>

    <div
      v-if="isScrollable && showLeftButton && !disabled"
      class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-1"
      :class="buttonOffsetClass"
    >
      <div class="absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-[#0f172a] via-[#0f172a]/90 to-transparent rounded-l-xl"></div>
      <button
        type="button"
        class="pointer-events-auto relative z-10 flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/30 bg-slate-900/85 text-cyan-300 shadow-[0_0_14px_rgba(34,211,238,0.2)] transition-all hover:border-cyan-300/60 hover:text-cyan-200"
        @mousedown.prevent="startScroll('left')"
        @mouseup="stopScroll"
        @mouseleave="stopScroll"
        @touchstart.prevent="startScroll('left')"
        @touchend="stopScroll"
        @touchcancel="stopScroll"
        @click.stop="nudgeScroll('left')"
      >
        <ChevronLeft :size="16" />
      </button>
    </div>

    <div
      v-if="isScrollable && showRightButton && !disabled"
      class="pointer-events-none absolute inset-y-0 right-0 flex items-center justify-end pr-1"
      :class="buttonOffsetClass"
    >
      <div class="absolute inset-y-0 right-0 w-14 bg-gradient-to-l from-[#0f172a] via-[#0f172a]/90 to-transparent rounded-r-xl"></div>
      <button
        type="button"
        class="pointer-events-auto relative z-10 flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/30 bg-slate-900/85 text-cyan-300 shadow-[0_0_14px_rgba(34,211,238,0.2)] transition-all hover:border-cyan-300/60 hover:text-cyan-200"
        @mousedown.prevent="startScroll('right')"
        @mouseup="stopScroll"
        @mouseleave="stopScroll"
        @touchstart.prevent="startScroll('right')"
        @touchend="stopScroll"
        @touchcancel="stopScroll"
        @click.stop="nudgeScroll('right')"
      >
        <ChevronRight :size="16" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}

.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
