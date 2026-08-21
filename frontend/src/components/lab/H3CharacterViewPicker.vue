<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CheckCircle2, Images, UserRound } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import type { CharacterReference, CharacterReferenceView } from '@/api/characters'
import type { UploadedReference } from '@/composables/lab-workbench/types'
import { useCharactersStore } from '@/stores/characters'

const props = defineProps<{
  references: UploadedReference[]
  maxItems: number
}>()

const emit = defineEmits<{
  select: [reference: UploadedReference]
}>()

const { t } = useI18n()
const store = useCharactersStore()
const open = ref(false)

const eligibleCharacters = computed(() => store.items.filter(character => (
  character.status === 'ready'
  && character.moderation_status === 'active'
  && availableViews(character).length > 0
)))
const selectedCount = computed(() => props.references.length)

const availableViews = (character: CharacterReference): CharacterReferenceView[] => (
  character.views.filter(view => (
    view.status === 'ready'
    && Boolean(view.preview_url)
    && Boolean(view.object_key)
  ))
)

const isSelected = (characterId: string, viewType: CharacterReferenceView['type']) => (
  props.references.some(item => (
    item.referenceRef?.source === 'private_character_view'
    && item.referenceRef.character_id === characterId
    && item.referenceRef.view_type === viewType
  ))
)

const selectView = (
  characterId: string,
  characterName: string,
  view: CharacterReferenceView,
) => {
  if (!view.preview_url || isSelected(characterId, view.type) || selectedCount.value >= props.maxItems) return
  emit('select', {
    key: `character:${characterId}:${view.type}`,
    preview: view.preview_url,
    name: `${characterName} · ${view.label}`,
    referenceRef: {
      source: 'private_character_view',
      character_id: characterId,
      view_type: view.type,
    },
  })
}

onMounted(() => void store.refresh())
</script>

<template>
  <div>
    <a-button class="rounded-xl" :disabled="selectedCount >= maxItems" @click="open = true">
      <span class="inline-flex items-center gap-2">
        <UserRound :size="16" />
        {{ t('characters.h3_picker.open') }}
      </span>
    </a-button>
    <span class="ml-2 text-xs opacity-65">
      {{ t('characters.h3_picker.count', { count: selectedCount, max: maxItems }) }}
    </span>

    <a-modal
      v-model:open="open"
      :title="t('characters.h3_picker.title')"
      :footer="null"
      :width="900"
      data-testid="h3-character-picker"
    >
      <p class="mb-4 text-sm leading-6 opacity-70">{{ t('characters.h3_picker.hint') }}</p>
      <div v-if="store.loading && eligibleCharacters.length === 0" class="py-12 text-center"><a-spin /></div>
      <div v-else-if="eligibleCharacters.length === 0" class="rounded-2xl border border-dashed p-10 text-center opacity-70">
        <Images :size="32" class="mx-auto mb-3" />
        {{ t('characters.h3_picker.empty') }}
      </div>
      <div v-else class="max-h-[65vh] space-y-5 overflow-y-auto pr-1">
        <section v-for="character in eligibleCharacters" :key="character.id">
          <div class="mb-2 font-semibold">{{ character.name }}</div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <button
              v-for="view in availableViews(character)"
              :key="`${character.id}:${view.type}`"
              type="button"
              class="h3-character-picker__view relative overflow-hidden rounded-2xl border text-left"
              :class="{ 'h3-character-picker__view--selected': isSelected(character.id, view.type) }"
              :disabled="isSelected(character.id, view.type) || selectedCount >= maxItems"
              :data-testid="`select-character-view-${character.id}-${view.type}`"
              @click="selectView(character.id, character.name, view)"
            >
              <img :src="view.preview_url ?? ''" :alt="`${character.name} · ${view.label}`" class="aspect-[4/5] w-full object-contain" />
              <div class="flex items-center justify-between gap-1 px-2 py-2 text-xs font-semibold">
                <span class="truncate">{{ view.label }}</span>
                <CheckCircle2 v-if="isSelected(character.id, view.type)" :size="15" class="shrink-0 text-emerald-400" />
              </div>
            </button>
          </div>
        </section>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.h3-character-picker__view {
  background: var(--theme-pill-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
}

.h3-character-picker__view:hover:not(:disabled),
.h3-character-picker__view--selected {
  border-color: var(--theme-tab-active-border);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-tab-active-shadow);
}

.h3-character-picker__view:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}
</style>
