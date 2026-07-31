<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ImagePlus, Pencil, RefreshCw, Sparkles, Trash2, UserRound } from 'lucide-vue-next'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type {
  CharacterReference,
  CharacterReferenceView,
  CharacterViewEngine,
  CharacterViewType,
} from '@/api/characters'
import {
  CHARACTER_VIEW_ENGINE_OPTIONS,
  getCharacterViewEngineCost,
} from '@/features/characters/characterViewEngines'
import { useCharactersStore } from '@/stores/characters'

const VIEW_TYPES: CharacterViewType[] = [
  'face_front',
  'face_side',
  'face_three_quarter',
  'body_front',
  'body_side',
  'body_back',
]

const { t } = useI18n()
const router = useRouter()
const store = useCharactersStore()
const selectedCharacterId = ref<string | null>(null)
const selectedViewType = ref<CharacterViewType>('face_front')
const selectedEngine = ref<CharacterViewEngine>('free_edit_v2_5')
const regenerating = ref(false)
const saving = ref(false)
const editingCharacterId = ref<string | null>(null)
const savingMetadata = ref(false)
const deletingCharacterId = ref<string | null>(null)
const metadataForm = reactive({
  name: '',
  description: '',
})
const prompts = reactive<Record<string, string>>({})
let pollTimer: ReturnType<typeof setTimeout> | null = null

const characters = computed(() => store.items)
const selectedCharacter = computed<CharacterReference | null>(() => (
  store.items.find(item => item.id === selectedCharacterId.value) ?? null
))
const selectedView = computed<CharacterReferenceView | null>(() => (
  selectedCharacter.value?.views.find(view => view.type === selectedViewType.value) ?? null
))
const readyCount = computed(() => (
  selectedCharacter.value?.views.filter(view => view.status === 'ready').length ?? 0
))
const hasPending = computed(() => (
  store.items.some(character => character.views.some(view => view.status === 'pending'))
))
const promptKey = computed(() => (
  selectedCharacter.value ? `${selectedCharacter.value.id}:${selectedViewType.value}` : ''
))
const selectedPrompt = computed({
  get: () => prompts[promptKey.value] ?? selectedView.value?.prompt ?? selectedView.value?.default_prompt ?? '',
  set: value => {
    if (promptKey.value) prompts[promptKey.value] = value
  },
})
const selectedEngineCost = computed(() => getCharacterViewEngineCost(selectedEngine.value))

const schedulePoll = () => {
  if (pollTimer) clearTimeout(pollTimer)
  if (hasPending.value) {
    pollTimer = setTimeout(async () => {
      await store.refresh()
      schedulePoll()
    }, 4000)
  }
}

const selectView = (character: CharacterReference, view: CharacterReferenceView) => {
  selectedCharacterId.value = character.id
  selectedViewType.value = view.type
  prompts[`${character.id}:${view.type}`] = view.prompt || view.default_prompt
}

const regenerate = async () => {
  if (!selectedCharacter.value || !selectedView.value || !selectedPrompt.value.trim()) return
  regenerating.value = true
  try {
    await store.generateView(
      selectedCharacter.value.id,
      selectedView.value.type,
      selectedPrompt.value.trim(),
      selectedEngine.value,
      selectedView.value.label,
    )
    message.success(t('characters.view_submitted', { view: selectedView.value.label }))
    schedulePoll()
  } finally {
    regenerating.value = false
  }
}

const saveReference = async () => {
  if (!selectedCharacter.value || readyCount.value < 2) return
  saving.value = true
  try {
    await store.saveReference(selectedCharacter.value.id)
    message.success(t('characters.reference_updated'))
  } finally {
    saving.value = false
  }
}

const createCharacter = () => (
  router.push({ name: 'CustomFeatures', query: { type: 'character_reference' } })
)

const openMetadataEditor = (character: CharacterReference) => {
  editingCharacterId.value = character.id
  metadataForm.name = character.name
  metadataForm.description = character.description ?? ''
}

const closeMetadataEditor = () => {
  if (savingMetadata.value) return
  editingCharacterId.value = null
}

const handleEditorOpenChange = (value: boolean) => {
  if (!value) closeMetadataEditor()
}

const saveMetadata = async () => {
  const characterId = editingCharacterId.value
  const name = metadataForm.name.trim()
  if (!characterId || !name) return
  savingMetadata.value = true
  try {
    await store.rename(characterId, {
      name,
      description: metadataForm.description.trim(),
    })
    editingCharacterId.value = null
    message.success(t('characters.details_updated'))
  } finally {
    savingMetadata.value = false
  }
}

const confirmDelete = (character: CharacterReference) => {
  Modal.confirm({
    title: t('characters.delete_confirm_named', { name: character.name }),
    content: t('characters.delete_confirm_hint'),
    okText: t('characters.delete'),
    okButtonProps: { danger: true },
    cancelText: t('characters.cancel'),
    async onOk() {
      deletingCharacterId.value = character.id
      try {
        await store.remove(character.id)
        if (selectedCharacterId.value === character.id) {
          selectedCharacterId.value = null
        }
        message.success(t('characters.deleted'))
      } finally {
        deletingCharacterId.value = null
      }
    },
  })
}

watch(hasPending, schedulePoll)
onMounted(async () => {
  await store.refresh()
  schedulePoll()
})
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <section class="character-library space-y-5">
    <div class="character-library__hero flex flex-col gap-4 rounded-3xl border p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <div class="flex items-start gap-3">
        <div class="character-library__icon flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl">
          <UserRound :size="22" />
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-400">
            {{ t('characters.library_eyebrow') }}
          </div>
          <h2 class="mt-1 text-xl font-bold">{{ t('characters.title') }}</h2>
          <p class="mt-1 text-sm leading-6 opacity-75">{{ t('characters.library_description') }}</p>
        </div>
      </div>
      <a-button type="primary" size="large" class="inline-flex items-center justify-center gap-2 rounded-2xl" @click="createCharacter">
        <span class="character-library__button-content items-center justify-center gap-2">
          <Sparkles :size="17" />
          {{ t('characters.create_in_lab') }}
        </span>
      </a-button>
    </div>

    <div v-if="store.loading && characters.length === 0" class="py-16 text-center">
      <a-spin />
    </div>
    <div v-else-if="characters.length === 0" class="character-library__empty rounded-3xl border p-12 text-center">
      <ImagePlus :size="42" class="mx-auto opacity-50" />
      <div class="mt-4 text-lg font-semibold">{{ t('characters.library_empty') }}</div>
      <div class="mt-2 text-sm opacity-70">{{ t('characters.library_empty_hint') }}</div>
    </div>

    <template v-else>
    <article
      v-for="character in characters"
      :key="character.id"
      class="character-library__card mb-5 overflow-hidden rounded-3xl border"
    >
      <div class="grid lg:grid-cols-[300px_minmax(0,1fr)]">
        <div class="character-library__sheet flex min-h-[250px] items-center justify-center border-b p-3 lg:border-b-0 lg:border-r">
          <img
            v-if="character.preview_url"
            :src="character.preview_url"
            :alt="character.name"
            class="max-h-[310px] w-full object-contain"
          />
          <div v-else class="text-center opacity-65">
            <RefreshCw v-if="character.views.some(view => view.status === 'pending')" :size="34" class="mx-auto animate-spin" />
            <ImagePlus v-else :size="34" class="mx-auto" />
            <div class="mt-3 text-sm">{{ t(`characters.status_${character.status}`) }}</div>
          </div>
        </div>

        <div class="min-w-0 p-4 sm:p-5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <h3 class="text-lg font-bold">{{ character.name }}</h3>
              <p v-if="character.description" class="mt-1 text-sm opacity-70">{{ character.description }}</p>
            </div>
            <div class="character-library__management flex flex-wrap items-center justify-end gap-2">
              <span class="character-library__status rounded-full border px-3 py-1 text-xs font-semibold">
                {{ t(`characters.status_${character.status}`) }}
              </span>
              <a-button
                size="small"
                class="inline-flex items-center gap-1.5 rounded-xl"
                :data-testid="`edit-character-${character.id}`"
                @click="openMetadataEditor(character)"
              >
                <span class="character-library__button-content items-center gap-1.5">
                  <Pencil :size="14" />
                  {{ t('characters.edit_details') }}
                </span>
              </a-button>
              <a-button
                danger
                size="small"
                class="inline-flex items-center gap-1.5 rounded-xl"
                :disabled="character.status === 'pending'"
                :loading="deletingCharacterId === character.id"
                :data-testid="`delete-character-${character.id}`"
                @click="confirmDelete(character)"
              >
                <span class="character-library__button-content items-center gap-1.5">
                  <Trash2 :size="14" />
                  {{ t('characters.delete') }}
                </span>
              </a-button>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
            <button
              v-for="view in character.views"
              :key="view.type"
              type="button"
              class="character-library__view overflow-hidden rounded-2xl border text-left"
              :class="{ 'character-library__view--active': selectedCharacterId === character.id && selectedViewType === view.type }"
              @click="selectView(character, view)"
            >
              <div class="aspect-[4/5]">
                <img v-if="view.preview_url" :src="view.preview_url" class="h-full w-full object-cover" />
                <div v-else class="flex h-full items-center justify-center">
                  <RefreshCw v-if="view.status === 'pending'" :size="18" class="animate-spin text-cyan-400" />
                  <ImagePlus v-else :size="18" class="opacity-45" />
                </div>
              </div>
              <div class="truncate px-2 py-2 text-[11px] font-semibold">{{ view.label }}</div>
            </button>
          </div>

          <div
            v-if="selectedCharacterId === character.id && selectedView"
            class="character-library__editor mt-4 rounded-2xl border p-4"
          >
            <div class="mb-2 flex items-center justify-between gap-2">
              <div class="text-sm font-semibold">
                {{ t('characters.regenerate_named_view', { view: selectedView.label }) }}
              </div>
              <button
                type="button"
                class="text-xs font-semibold text-cyan-400 hover:text-cyan-300"
                @click="selectedPrompt = selectedView.default_prompt"
              >
                {{ t('characters.restore_default') }}
              </button>
            </div>
            <a-textarea
              v-model:value="selectedPrompt"
              :maxlength="1200"
              :auto-size="{ minRows: 4, maxRows: 8 }"
            />
            <div class="mt-3">
              <div class="mb-2 text-xs font-semibold">
                {{ t('characters.engine_label') }}
              </div>
              <a-radio-group
                v-model:value="selectedEngine"
                button-style="solid"
                class="flex flex-wrap gap-2"
              >
                <a-radio-button
                  v-for="option in CHARACTER_VIEW_ENGINE_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ t(option.labelKey) }} · {{ option.cost }} {{ t('app.credits') }}
                </a-radio-button>
              </a-radio-group>
            </div>
            <div class="mt-3 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <a-button
                :disabled="readyCount < 2 || character.views.some(view => view.status === 'pending')"
                :loading="saving"
                class="rounded-xl"
                @click="saveReference"
              >
                {{ t('characters.update_reference') }}
              </a-button>
              <a-button
                type="primary"
                :disabled="!selectedPrompt.trim() || selectedView.status === 'pending'"
                :loading="regenerating || selectedView.status === 'pending'"
                class="rounded-xl"
                @click="regenerate"
              >
                {{ t('characters.regenerate_view') }} · {{ selectedEngineCost }} {{ t('app.credits') }}
              </a-button>
            </div>
          </div>
        </div>
      </div>
    </article>
    </template>

    <a-modal
      :open="editingCharacterId !== null"
      :title="t('characters.edit_details_title')"
      :confirm-loading="savingMetadata"
      :ok-button-props="{ disabled: !metadataForm.name.trim() }"
      :ok-text="t('characters.save_changes')"
      :cancel-text="t('characters.cancel')"
      @ok="saveMetadata"
      @cancel="closeMetadataEditor"
      @update:open="handleEditorOpenChange"
    >
      <div class="space-y-4 py-2">
        <label class="block">
          <span class="mb-2 block text-sm font-semibold">{{ t('characters.name_label') }}</span>
          <a-input
            v-model:value="metadataForm.name"
            data-testid="edit-character-name"
            :maxlength="60"
            :placeholder="t('characters.name_placeholder')"
            @press-enter="saveMetadata"
          />
        </label>
        <label class="block">
          <span class="mb-2 block text-sm font-semibold">{{ t('characters.description_label') }}</span>
          <a-textarea
            v-model:value="metadataForm.description"
            data-testid="edit-character-description"
            :maxlength="500"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            :placeholder="t('characters.description_placeholder')"
          />
        </label>
        <p class="text-xs leading-5 opacity-60">{{ t('characters.edit_details_hint') }}</p>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.character-library {
  color: var(--theme-text-primary);
}

.character-library__hero,
.character-library__card,
.character-library__empty {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  box-shadow: var(--theme-shadow);
}

.character-library__hero {
  background:
    radial-gradient(circle at 90% 0%, rgba(34, 211, 238, 0.14), transparent 35%),
    var(--theme-card-bg);
}

.character-library__icon {
  background: rgba(34, 211, 238, 0.13);
  border: 1px solid rgba(34, 211, 238, 0.32);
  color: #67e8f9;
}

.character-library__button-content {
  display: inline-flex;
}

.character-library__sheet {
  background: var(--theme-panel-strong-bg);
  border-color: var(--theme-border);
}

.character-library__status,
.character-library__editor {
  background: var(--theme-card-strong-bg);
  border-color: var(--theme-border);
}

@media (max-width: 639px) {
  .character-library__management {
    width: 100%;
    justify-content: flex-start;
  }
}

.character-library__view {
  background: var(--theme-pill-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
  transition: 160ms ease;
}

.character-library__view:hover,
.character-library__view--active {
  border-color: var(--theme-tab-active-border);
  color: var(--theme-text-primary);
}

.character-library__view--active {
  box-shadow: var(--theme-tab-active-shadow);
}
</style>
