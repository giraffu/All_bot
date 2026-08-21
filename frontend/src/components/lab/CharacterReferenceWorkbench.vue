<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { CheckCircle2, ImagePlus, RefreshCw, Sparkles } from 'lucide-vue-next'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type {
  CharacterReference,
  CharacterReferenceView,
  CharacterPromptProfile,
  CharacterViewEngine,
  CharacterViewType,
} from '@/api/characters'
import { useUpload } from '@/composables/useUpload'
import { getMissingCharacterViewTypes } from '@/features/characters/characterBatchGeneration'
import {
  CHARACTER_VIEW_ENGINE_OPTIONS,
  getCharacterViewEngineCost,
} from '@/features/characters/characterViewEngines'
import { useCharactersStore } from '@/stores/characters'
import { WEB_CHARACTER_EXPLICIT_VIEWS_ENABLED } from '@/features/generation/labModeConfig'

type ViewDefinition = {
  type: CharacterViewType
  labelKey: string
}

const REQUIRED_VIEW_DEFINITIONS: ViewDefinition[] = [
  {
    type: 'face_front',
    labelKey: 'characters.views.face_front',
  },
  {
    type: 'body_front',
    labelKey: 'characters.views.body_front',
  },
  {
    type: 'body_side',
    labelKey: 'characters.views.body_side',
  },
  {
    type: 'body_back',
    labelKey: 'characters.views.body_back',
  },
]
const EXPLICIT_VIEW_DEFINITION: ViewDefinition = {
  type: 'genitals_front',
  labelKey: 'characters.views.genitals_front',
}
const GENDER_OPTIONS = ['female', 'male'] as const

const { t } = useI18n()
const store = useCharactersStore()
const { uploading, uploadFile } = useUpload()
const name = ref('')
const description = ref('')
const promptProfile = reactive<Required<CharacterPromptProfile>>({
  gender: 'female',
  breast_size: 'natural',
  pubic_hair: 'natural',
  skin_tone: 'asian_yellow',
})
const sourceKey = ref<string | null>(null)
const sourcePreview = ref<string | null>(null)
const draftId = ref<string | null>(null)
const activeViewType = ref<CharacterViewType>('face_front')
const creatingDraft = ref(false)
const generatingView = ref<CharacterViewType | null>(null)
const uploadingView = ref<CharacterViewType | null>(null)
const selectedEngine = ref<CharacterViewEngine>('free_edit_v2_5')
const prompts = reactive<Record<CharacterViewType, string>>(
  Object.fromEntries(
    [...REQUIRED_VIEW_DEFINITIONS, EXPLICIT_VIEW_DEFINITION].map(view => [view.type, '']),
  ) as Record<CharacterViewType, string>,
)

const draft = computed<CharacterReference | null>(() => (
  store.items.find(item => item.id === draftId.value) ?? null
))
const viewMap = computed(() => new Map(
  (draft.value?.views ?? []).map(view => [view.type, view]),
))
const viewDefinitions = computed(() => (
  WEB_CHARACTER_EXPLICIT_VIEWS_ENABLED
    ? [...REQUIRED_VIEW_DEFINITIONS, EXPLICIT_VIEW_DEFINITION]
    : REQUIRED_VIEW_DEFINITIONS
))
const activeDefinition = computed(() => (
  viewDefinitions.value.find(view => view.type === activeViewType.value)!
))
const activeView = computed<CharacterReferenceView | undefined>(() => (
  viewMap.value.get(activeViewType.value)
))
const activeViewConfig = computed(() => (
  draft.value?.view_configs?.find(config => config.type === activeViewType.value)
))
const viewLabel = (definition: ViewDefinition) => (
  draft.value?.view_configs?.find(config => config.type === definition.type)?.label
  ?? t(definition.labelKey)
)
const readyCount = computed(() => (
  REQUIRED_VIEW_DEFINITIONS.filter(definition => (
    viewMap.value.get(definition.type)?.status === 'ready'
  )).length
))
const hasPendingView = computed(() => (
  draft.value?.views.some(view => view.status === 'pending') ?? false
))
const batchState = computed(() => draftId.value ? store.batchRuns?.[draftId.value] : undefined)
const batchGenerating = computed(() => batchState.value?.running ?? false)
const batchSubmitted = computed(() => batchState.value?.submitted ?? 0)
const batchTotal = computed(() => batchState.value?.total ?? 0)
const selectedEngineCost = computed(() => getCharacterViewEngineCost(selectedEngine.value))
const missingViewTypes = computed(() => getMissingCharacterViewTypes(
  REQUIRED_VIEW_DEFINITIONS.map(view => view.type),
  draft.value?.views ?? [],
))
const batchEstimatedCost = computed(() => (
  missingViewTypes.value.length * selectedEngineCost.value
))
const genitalGenerationBlocked = computed(() => (
  activeViewType.value === 'genitals_front'
  && viewMap.value.get('body_front')?.status !== 'ready'
))

const profilePayload = computed<CharacterPromptProfile>(() => (
  promptProfile.gender === 'male'
    ? { gender: 'male' }
    : {
        gender: 'female',
        breast_size: promptProfile.breast_size,
        pubic_hair: promptProfile.pubic_hair,
        skin_tone: promptProfile.skin_tone,
      }
))

const restorePrompt = (viewType: CharacterViewType) => {
  prompts[viewType] = draft.value?.default_prompts?.[viewType] ?? ''
}
const selectGender = (gender: 'female' | 'male') => {
  promptProfile.gender = gender
}
const selectFemaleTag = async (
  key: 'breast_size' | 'pubic_hair' | 'skin_tone',
  value: string,
) => {
  const previousDefaults = { ...(draft.value?.default_prompts ?? {}) }
  if (key === 'breast_size') {
    promptProfile.breast_size = value as Required<CharacterPromptProfile>['breast_size']
  } else if (key === 'pubic_hair') {
    promptProfile.pubic_hair = value as Required<CharacterPromptProfile>['pubic_hair']
  } else {
    promptProfile.skin_tone = value as Required<CharacterPromptProfile>['skin_tone']
  }
  if (draftId.value) {
    await store.rename(draftId.value, { prompt_profile: profilePayload.value })
    for (const definition of viewDefinitions.value) {
      const previousDefault = previousDefaults[definition.type]
      if (!prompts[definition.type] || prompts[definition.type] === previousDefault) {
        restorePrompt(definition.type)
      }
    }
  }
}

const beforeUpload = async (file: File) => {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    message.error(t('characters.image_type_error'))
    return false
  }
  sourceKey.value = await uploadFile(file, {
    maxSizeBytes: 20 * 1024 * 1024,
    maxSizeLabel: '20MB',
  })
  if (sourcePreview.value) URL.revokeObjectURL(sourcePreview.value)
  sourcePreview.value = sourceKey.value ? URL.createObjectURL(file) : null
  return false
}

const createDraft = async () => {
  if (!name.value.trim() || !sourceKey.value) return
  const characterDescription = description.value.trim()
  if (!characterDescription) {
    message.error(t('characters.description_required'))
    return
  }
  creatingDraft.value = true
  try {
    const created = await store.createDraft({
      name: name.value.trim(),
      description: characterDescription,
      source_object_key: sourceKey.value,
      prompt_profile: profilePayload.value,
      adult_confirmed: true,
      usage_rights_confirmed: true,
    })
    draftId.value = created.id
    for (const definition of viewDefinitions.value) {
      prompts[definition.type] = created.default_prompts?.[definition.type] ?? ''
    }
    message.success(t('characters.draft_created'))
  } finally {
    creatingDraft.value = false
  }
}

const generateView = async () => {
  if (!draftId.value) return
  const prompt = prompts[activeViewType.value].trim()
  if (!prompt) {
    message.warning(t('characters.view_prompt_required'))
    return
  }
  generatingView.value = activeViewType.value
  try {
    await store.generateView(
      draftId.value,
      activeViewType.value,
      prompt,
      selectedEngine.value,
      viewLabel(activeDefinition.value),
    )
    message.success(t('characters.view_submitted', {
      view: viewLabel(activeDefinition.value),
    }))
  } finally {
    generatingView.value = null
  }
}

const beforeViewUpload = async (file: File) => {
  if (!draftId.value) return false
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    message.error(t('characters.image_type_error'))
    return false
  }
  const viewType = activeViewType.value
  uploadingView.value = viewType
  try {
    const objectKey = await uploadFile(file, {
      maxSizeBytes: 20 * 1024 * 1024,
      maxSizeLabel: '20MB',
    })
    if (!objectKey || !draftId.value) return false
    await store.uploadView(draftId.value, viewType, objectKey)
    message.success(t('characters.view_uploaded', {
      view: viewLabel(activeDefinition.value),
    }))
    await store.refresh()
  } finally {
    uploadingView.value = null
  }
  return false
}

const generateMissingViews = async () => {
  if (!draftId.value || batchGenerating.value) return
  const queuedViewTypes = [...missingViewTypes.value]
  if (queuedViewTypes.length === 0) return
  try {
    const result = await store.generateMissingViews(
      draftId.value,
      queuedViewTypes.map((viewType) => {
        const definition = REQUIRED_VIEW_DEFINITIONS.find(view => view.type === viewType)!
        const prompt = prompts[viewType].trim()
        if (!prompt) throw new Error(`Missing prompt for ${viewType}`)
        return { type: viewType, prompt, label: viewLabel(definition) }
      }),
      selectedEngine.value,
    )
    if (result && !result.cancelled) {
      if (result.failed > 0) {
        message.warning(t('characters.batch_submitted_with_failures', {
          submitted: result.submitted,
          failed: result.failed,
        }))
      } else {
        message.success(t('characters.batch_submitted', {
          count: result.submitted,
        }))
      }
    }
  } catch (error) {
    console.error('Failed to batch-generate character views:', error)
    message.error(t('characters.batch_submit_failed'))
  }
}

const resetWorkspace = () => {
  draftId.value = null
  name.value = ''
  description.value = ''
  sourceKey.value = null
  if (sourcePreview.value) URL.revokeObjectURL(sourcePreview.value)
  sourcePreview.value = null
  activeViewType.value = 'face_front'
  selectedEngine.value = 'free_edit_v2_5'
  promptProfile.gender = 'female'
  promptProfile.breast_size = 'natural'
  promptProfile.pubic_hair = 'natural'
  promptProfile.skin_tone = 'asian_yellow'
  for (const definition of [...REQUIRED_VIEW_DEFINITIONS, EXPLICIT_VIEW_DEFINITION]) {
    prompts[definition.type] = ''
  }
}

onMounted(() => void store.refresh())
onBeforeUnmount(() => {
  if (sourcePreview.value) URL.revokeObjectURL(sourcePreview.value)
})
</script>

<template>
  <section class="character-workbench overflow-hidden rounded-[28px] border">
    <header class="character-workbench__hero px-5 py-5 sm:px-7">
      <div class="flex items-start gap-3">
        <div class="character-workbench__icon flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl">
          <Sparkles :size="22" />
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">
            {{ t('characters.lab_eyebrow') }}
          </div>
          <h2 class="mt-1 text-xl font-bold sm:text-2xl">
            {{ t('characters.lab_title') }}
          </h2>
          <p class="mt-2 max-w-3xl text-sm leading-6">
            {{ t('characters.lab_description') }}
          </p>
        </div>
      </div>
    </header>

    <div v-if="!draft" class="grid gap-5 p-5 sm:p-7 lg:grid-cols-[280px_minmax(0,1fr)]">
      <a-upload
        class="character-workbench__upload"
        :show-upload-list="false"
        :before-upload="beforeUpload"
        accept="image/png,image/jpeg,image/webp"
      >
        <div class="character-workbench__source flex aspect-[4/5] w-full cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border border-dashed">
          <img v-if="sourcePreview" :src="sourcePreview" class="h-full w-full object-contain" />
          <template v-else>
            <ImagePlus :size="34" />
            <span class="mt-3 text-sm font-semibold">{{ t('characters.upload_source') }}</span>
            <span class="mt-1 text-xs">{{ t('characters.upload_hint') }}</span>
          </template>
        </div>
      </a-upload>

      <div class="flex flex-col justify-center space-y-4">
        <div>
          <div class="mb-2 text-sm font-semibold">{{ t('characters.name_label') }}</div>
          <a-input
            v-model:value="name"
            size="large"
            :maxlength="60"
            :placeholder="t('characters.name_placeholder')"
          />
        </div>
        <div>
          <div class="mb-2 text-sm font-semibold">{{ t('characters.description_label') }}</div>
          <a-textarea
            v-model:value="description"
            :maxlength="500"
            :auto-size="{ minRows: 3, maxRows: 5 }"
            :placeholder="t('characters.description_placeholder')"
          />
        </div>
        <div class="character-workbench__profile rounded-3xl border p-4 sm:p-5">
          <div class="mb-3">
            <div>
              <div class="text-sm font-semibold">{{ t('characters.profile_title') }}</div>
              <div class="mt-1 text-xs opacity-70">{{ t('characters.profile_hint') }}</div>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2" data-testid="gender-options">
            <button
              v-for="gender in GENDER_OPTIONS"
              :key="gender"
              type="button"
              class="character-workbench__choice rounded-2xl border px-4 py-3 text-left"
              :class="{ 'character-workbench__choice--active': promptProfile.gender === gender }"
              @click="selectGender(gender)"
            >
              <div class="font-semibold">{{ t(`characters.gender.${gender}`) }}</div>
              <div class="mt-1 text-xs opacity-70">{{ t(`characters.gender.${gender}_hint`) }}</div>
            </button>
          </div>
        </div>
        <div class="character-workbench__notice rounded-2xl px-4 py-3 text-sm leading-6">
          {{ t('characters.billing_hint') }}
        </div>
        <a-button
          type="primary"
          size="large"
          class="h-12 rounded-2xl font-semibold"
          :disabled="!name.trim() || !description.trim() || !sourceKey"
          :loading="creatingDraft || uploading"
          @click="createDraft"
        >
          {{ t('characters.start_views') }}
        </a-button>
      </div>
    </div>

    <div v-else class="p-4 sm:p-6">
      <div class="character-workbench__progress mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3">
        <div>
          <div class="font-semibold">{{ draft.name }}</div>
          <div class="mt-1 text-xs">
            {{ t('characters.ready_progress', { ready: readyCount, total: REQUIRED_VIEW_DEFINITIONS.length }) }}
          </div>
        </div>
        <a-button size="small" class="rounded-full" @click="resetWorkspace">
          {{ t('characters.new_character') }}
        </a-button>
      </div>

      <div class="character-workbench__tabs mb-5 grid grid-cols-2 gap-2 lg:grid-cols-5">
        <button
          v-for="definition in viewDefinitions"
          :key="definition.type"
          type="button"
          class="character-workbench__tab rounded-2xl border px-3 py-3 text-left"
          :class="{ 'character-workbench__tab--active': activeViewType === definition.type }"
          @click="activeViewType = definition.type"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-semibold">{{ viewLabel(definition) }}</span>
            <CheckCircle2
              v-if="viewMap.get(definition.type)?.status === 'ready'"
              :size="16"
              class="text-emerald-400"
            />
            <RefreshCw
              v-else-if="viewMap.get(definition.type)?.status === 'pending'"
              :size="16"
              class="animate-spin text-cyan-400"
            />
          </div>
          <div class="mt-1 text-[11px]">
            {{ t(`characters.view_status_${viewMap.get(definition.type)?.status || 'empty'}`) }}
          </div>
        </button>
      </div>

      <div
        v-if="activeViewType === 'genitals_front'"
        class="character-workbench__notice mb-5 rounded-2xl px-4 py-3 text-sm leading-6"
      >
        {{ t('characters.explicit_view_disclaimer') }}
        <span v-if="genitalGenerationBlocked" class="block font-semibold text-amber-400">
          {{ t('characters.genital_body_front_required') }}
        </span>
      </div>

      <div class="grid gap-5 lg:grid-cols-[minmax(260px,0.8fr)_minmax(0,1.2fr)]">
        <div class="character-workbench__preview flex min-h-[360px] items-center justify-center overflow-hidden rounded-3xl border">
          <img
            v-if="activeView?.preview_url"
            :src="activeView.preview_url"
            class="max-h-[560px] h-full w-full object-contain"
          />
          <div v-else class="px-6 text-center">
            <ImagePlus :size="40" class="mx-auto opacity-60" />
            <div class="mt-3 font-semibold">{{ viewLabel(activeDefinition) }}</div>
            <div class="mt-2 text-sm leading-6 opacity-70">
              {{ t('characters.view_empty_hint') }}
            </div>
          </div>
        </div>

        <div class="flex flex-col">
          <div class="mb-2 flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-semibold">{{ t('characters.view_prompt_label') }}</div>
              <div class="mt-1 text-xs opacity-70">{{ t('characters.view_prompt_hint') }}</div>
            </div>
            <a-button
              size="small"
              class="rounded-full"
              @click="restorePrompt(activeViewType)"
            >
              {{ t('characters.restore_default') }}
            </a-button>
          </div>
          <a-textarea
            v-model:value="prompts[activeViewType]"
            :maxlength="1200"
            :auto-size="{ minRows: 8, maxRows: 14 }"
            :placeholder="t('characters.view_prompt_placeholder')"
          />
          <div
            v-if="promptProfile.gender === 'female' && activeViewConfig?.tag_groups.length"
            class="character-workbench__profile mt-4 grid gap-4 rounded-2xl border p-4"
            data-testid="active-view-options"
          >
            <div class="text-sm font-semibold">{{ t('characters.active_view_tags') }}</div>
            <div v-for="group in activeViewConfig.tag_groups" :key="group">
              <div class="mb-2 text-xs font-semibold opacity-75">{{ t(`characters.profile_groups.${group}`) }}</div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="(_, value) in activeViewConfig.tag_options[group]"
                  :key="value"
                  type="button"
                  class="character-workbench__pill rounded-full border px-3 py-2 text-xs font-semibold"
                  :class="{ 'character-workbench__pill--active': promptProfile[group] === value }"
                  @click="selectFemaleTag(group, String(value))"
                >
                  {{ t(`characters.profile_options.${group}.${String(value)}`) }}
                </button>
              </div>
            </div>
          </div>
          <div class="mt-4">
            <div class="mb-2 text-sm font-semibold">
              {{ t('characters.engine_label') }}
            </div>
            <a-radio-group
              v-model:value="selectedEngine"
              button-style="solid"
              class="character-workbench__engines flex flex-wrap gap-2"
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
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <a-button
              type="primary"
              size="large"
              class="h-12 rounded-2xl font-semibold"
              :loading="generatingView === activeViewType || activeView?.status === 'pending'"
              :disabled="!prompts[activeViewType].trim() || genitalGenerationBlocked || hasPendingView || batchGenerating || uploadingView !== null"
              @click="generateView"
            >
              {{ activeView?.status === 'ready' ? t('characters.regenerate_view') : t('characters.generate_view') }}
              · {{ selectedEngineCost }} {{ t('app.credits') }}
            </a-button>
            <a-upload
              class="character-workbench__view-upload"
              :show-upload-list="false"
              :before-upload="beforeViewUpload"
              accept="image/png,image/jpeg,image/webp"
            >
              <a-button
                size="large"
                class="h-12 w-full rounded-2xl font-semibold"
                :loading="uploadingView === activeViewType"
                :disabled="activeView?.status === 'pending' || batchGenerating || generatingView !== null"
              >
                {{ activeView?.status === 'ready' ? t('characters.replace_view_upload') : t('characters.upload_view') }}
              </a-button>
            </a-upload>
          </div>
          <div class="mt-2 text-center text-xs opacity-70">
            {{ t('characters.upload_view_hint') }}
          </div>
          <a-button
            type="primary"
            ghost
            size="large"
            class="character-workbench__batch mt-3 h-12 rounded-2xl font-semibold"
            :loading="batchGenerating"
            :disabled="missingViewTypes.length === 0 || generatingView !== null"
            data-testid="generate-missing-views"
            @click="generateMissingViews"
          >
            <span class="inline-flex items-center justify-center gap-2">
              <template v-if="batchGenerating">
                {{ t('characters.batch_submitting', {
                  submitted: batchSubmitted,
                  total: batchTotal,
                }) }}
              </template>
              <template v-else>
                {{ t('characters.generate_missing_views', {
                  count: missingViewTypes.length,
                }) }}
                · {{ batchEstimatedCost }} {{ t('app.credits') }}
              </template>
            </span>
          </a-button>
          <div class="mt-2 text-center text-xs opacity-70">
            {{ t('characters.batch_concurrency_hint') }}
          </div>
          <div class="character-workbench__save mt-5 flex flex-col gap-3 rounded-2xl border p-4">
            <div>
              <div class="font-semibold">{{ t('characters.auto_save_reference_title') }}</div>
              <div class="mt-1 text-xs opacity-70">
                {{ draft.status === 'ready' ? t('characters.auto_saved_to_library') : t('characters.auto_save_in_progress') }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.character-workbench {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow);
}

.character-workbench__hero {
  background:
    radial-gradient(circle at 88% 10%, rgba(34, 211, 238, 0.16), transparent 32%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 41, 59, 0.84));
  border-bottom: 1px solid var(--theme-border);
  color: #f8fafc;
}

.character-workbench__hero p {
  color: rgba(226, 232, 240, 0.86);
}

.character-workbench__progress,
.character-workbench__tab,
.character-workbench__notice {
  color: var(--theme-text-secondary);
}

.character-workbench__icon {
  background: linear-gradient(145deg, rgba(59, 130, 246, 0.28), rgba(34, 211, 238, 0.18));
  border: 1px solid rgba(34, 211, 238, 0.35);
  color: #67e8f9;
}

.character-workbench__upload,
.character-workbench__upload :deep(.ant-upload-select),
.character-workbench__view-upload,
.character-workbench__view-upload :deep(.ant-upload-select) {
  display: block;
  width: 100%;
}

.character-workbench__upload {
  max-width: 260px;
  justify-self: center;
}

@media (min-width: 640px) {
  .character-workbench__upload {
    max-width: 280px;
  }
}

@media (min-width: 1024px) {
  .character-workbench__upload {
    max-width: none;
  }
}

.character-workbench__source,
.character-workbench__preview {
  background: var(--theme-panel-strong-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-text-secondary);
}

.character-workbench__notice,
.character-workbench__progress,
.character-workbench__save,
.character-workbench__profile {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.character-workbench__choice,
.character-workbench__pill {
  background: var(--theme-pill-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
  transition: 160ms ease;
}

.character-workbench__choice:hover,
.character-workbench__pill:hover {
  border-color: rgba(34, 211, 238, 0.6);
  color: var(--theme-text-primary);
}

.character-workbench__choice--active,
.character-workbench__pill--active {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(139, 92, 246, 0.16));
  border-color: rgba(34, 211, 238, 0.72);
  color: var(--theme-text-primary);
  box-shadow: 0 0 0 1px rgba(34, 211, 238, 0.12), 0 8px 24px rgba(14, 165, 233, 0.12);
}

.character-workbench__male-note {
  background: rgba(14, 165, 233, 0.09);
  color: var(--theme-text-secondary);
}

.character-workbench__tab {
  background: var(--theme-pill-bg);
  border-color: var(--theme-border);
  transition: 160ms ease;
}

.character-workbench__tab:hover {
  border-color: var(--theme-border-strong);
  color: var(--theme-text-primary);
}

.character-workbench__tab--active {
  background: var(--theme-tab-active-bg);
  border-color: var(--theme-tab-active-border);
  color: var(--theme-tab-active-text);
  box-shadow: var(--theme-tab-active-shadow);
}
</style>
