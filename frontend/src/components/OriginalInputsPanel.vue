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
    compact?: boolean
  }>(),
  {
    compact: false,
  },
)

const { t } = useI18n()
const previews = computed(() => resolveOriginalInputPreviews(props.source, t))
</script>

<template>
  <section
    v-if="previews.length"
    class="original-inputs-panel"
    :class="{ 'original-inputs-panel--compact': compact }"
  >
    <div class="original-inputs-panel__header">
      <ImageIcon :size="14" />
      <span>{{ $t('original_inputs.title') }}</span>
    </div>

    <div class="original-inputs-panel__grid">
      <div
        v-for="preview in previews"
        :key="preview.key"
        class="original-inputs-panel__item"
      >
        <div class="original-inputs-panel__media-wrap">
          <video
            v-if="preview.mediaType === 'video'"
            :src="preview.url"
            muted
            playsinline
            controls
            preload="metadata"
            class="original-inputs-panel__media"
          ></video>
          <img
            v-else
            :src="preview.url"
            :alt="preview.label"
            loading="lazy"
            class="original-inputs-panel__media"
          />
          <div class="original-inputs-panel__type">
            <Video v-if="preview.mediaType === 'video'" :size="13" />
            <ImageIcon v-else :size="13" />
          </div>
        </div>
        <div class="original-inputs-panel__label">
          {{ preview.label }}
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.original-inputs-panel {
  border: 1px solid var(--original-inputs-border, rgba(71, 85, 105, 0.9));
  background: var(--original-inputs-bg, rgba(15, 23, 42, 0.56));
  border-radius: 0.5rem;
  padding: 0.75rem;
  box-shadow: var(--original-inputs-shadow, inset 0 1px 0 rgba(148, 163, 184, 0.06));
}

.original-inputs-panel__header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--original-inputs-title, #f8fafc);
  font-size: 0.76rem;
  font-weight: 700;
  margin-bottom: 0.65rem;
}

.original-inputs-panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(5.5rem, 1fr));
  gap: 0.65rem;
}

.original-inputs-panel--compact .original-inputs-panel__grid {
  grid-template-columns: repeat(auto-fit, minmax(4.75rem, 1fr));
}

.original-inputs-panel__item {
  min-width: 0;
}

.original-inputs-panel__media-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: 0.5rem;
  border: 1px solid var(--original-inputs-media-border, rgba(100, 116, 139, 0.62));
  background: rgba(2, 6, 23, 0.36);
}

.original-inputs-panel__media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.original-inputs-panel__type {
  position: absolute;
  right: 0.35rem;
  top: 0.35rem;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #67e8f9;
  background: rgba(2, 6, 23, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.original-inputs-panel__label {
  color: var(--original-inputs-label, #cbd5e1);
  font-size: 0.72rem;
  font-weight: 600;
  margin-top: 0.4rem;
  overflow-wrap: anywhere;
}
</style>
