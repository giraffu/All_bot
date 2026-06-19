<script setup lang="ts">
import { computed } from 'vue'
import { Image as ImageIcon, Video } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import {
  resolveOriginalInputPreviews,
  type OriginalInputSource,
} from '@/utils/originalInputs'

const props = withDefaults(
  defineProps<{
    source: OriginalInputSource | null | undefined
    positionClass?: string
  }>(),
  {
    positionClass: 'absolute top-2 left-2 z-10',
  },
)

const { t } = useI18n()
const previews = computed(() => resolveOriginalInputPreviews(props.source, t))
const firstPreview = computed(() => previews.value[0] || null)
const extraCount = computed(() => Math.max(0, previews.value.length - 1))
</script>

<template>
  <div
    v-if="firstPreview"
    :class="positionClass"
    class="original-input-badge pointer-events-none"
    :title="$t('original_inputs.title')"
  >
    <div class="original-input-badge__stack">
      <div
        v-if="extraCount > 0"
        class="original-input-badge__shadow"
      ></div>
      <div class="original-input-badge__thumb">
        <video
          v-if="firstPreview.mediaType === 'video'"
          :src="firstPreview.url"
          muted
          playsinline
          preload="metadata"
          class="original-input-badge__media"
        ></video>
        <img
          v-else
          :src="firstPreview.url"
          :alt="firstPreview.label"
          loading="lazy"
          class="original-input-badge__media"
        />
        <div
          v-if="firstPreview.mediaType === 'video'"
          class="original-input-badge__type"
        >
          <Video :size="10" />
        </div>
        <div
          v-else
          class="original-input-badge__type"
        >
          <ImageIcon :size="10" />
        </div>
      </div>
      <div
        v-if="extraCount > 0"
        class="original-input-badge__count"
      >
        +{{ extraCount }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.original-input-badge__stack {
  position: relative;
  width: 2.55rem;
  height: 2.55rem;
}

.original-input-badge__shadow,
.original-input-badge__thumb {
  position: absolute;
  inset: 0;
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(15, 23, 42, 0.82);
  box-shadow: 0 10px 24px rgba(2, 6, 23, 0.34);
}

.original-input-badge__shadow {
  transform: translate(5px, 5px);
  border-color: rgba(34, 211, 238, 0.5);
  background: rgba(8, 47, 73, 0.78);
}

.original-input-badge__media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.original-input-badge__type {
  position: absolute;
  right: 0.2rem;
  top: 0.2rem;
  width: 1rem;
  height: 1rem;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #67e8f9;
  background: rgba(2, 6, 23, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.18);
}

.original-input-badge__count {
  position: absolute;
  right: -0.35rem;
  bottom: -0.35rem;
  min-width: 1.25rem;
  height: 1.25rem;
  border-radius: 999px;
  padding: 0 0.28rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ecfeff;
  background: #0891b2;
  border: 1px solid rgba(255, 255, 255, 0.72);
  font-size: 0.65rem;
  font-weight: 800;
  line-height: 1;
}
</style>
