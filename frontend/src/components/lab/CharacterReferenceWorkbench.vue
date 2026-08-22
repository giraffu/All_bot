<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { CheckCircle2, ImagePlus, RefreshCw, Sparkles } from 'lucide-vue-next'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type {
  CharacterReferenceView,
  CharacterViewEngine,
  CharacterViewType,
} from '@/api/characters'
import { useUpload } from '@/composables/useUpload'
import {
  CHARACTER_VIEW_ENGINE_OPTIONS,
  getCharacterViewEngineCost,
} from '@/features/characters/characterViewEngines'
import { useCharactersStore } from '@/stores/characters'
import { WEB_CHARACTER_EXPLICIT_VIEWS_ENABLED } from '@/features/generation/labModeConfig'

type ViewDefinition = { type: CharacterViewType; labelKey: string }

const VIEW_DEFINITIONS: ViewDefinition[] = [
  { type: 'face_front', labelKey: 'characters.views.face_front' },
  { type: 'body_front_nude', labelKey: 'characters.views.body_front_nude' },
  { type: 'body_front_clothed', labelKey: 'characters.views.body_front_clothed' },
  { type: 'torso_front', labelKey: 'characters.views.torso_front' },
  { type: 'genitals_front', labelKey: 'characters.views.genitals_front' },
  { type: 'pelvis_back', labelKey: 'characters.views.pelvis_back' },
  { type: 'custom_1', labelKey: 'characters.views.custom_1' },
  { type: 'custom_2', labelKey: 'characters.views.custom_2' },
  { type: 'custom_3', labelKey: 'characters.views.custom_3' },
  { type: 'custom_4', labelKey: 'characters.views.custom_4' },
]

const { t } = useI18n()
const store = useCharactersStore()
const { uploading, uploadFile } = useUpload()
const name = ref('')
const initialViewType = ref<CharacterViewType>('face_front')
const initialViewLabel = ref('')
const initialSourceKey = ref<string | null>(null)
const initialPreview = ref<string | null>(null)
const initialTemplateId = ref<string | null>(null)
const draftId = ref<string | null>(null)
const activeViewType = ref<CharacterViewType>('face_front')
const selectedEngine = ref<CharacterViewEngine>('free_edit_v2_5')
const creating = ref(false)
const generating = ref(false)
const applyingTemplate = ref(false)
const savingDetails = ref(false)
const characterForm = reactive({ description: '' })
const viewForm = reactive({ displayName: '', description: '', prompt: '' })
const selectedTemplateId = ref<string | null>(null)

const draft = computed(() => store.items.find(item => item.id === draftId.value) ?? null)
const viewMap = computed(() => new Map(
  (draft.value?.views ?? []).map(view => [view.type, view]),
))
const activeDefinition = computed(() => (
  VIEW_DEFINITIONS.find(item => item.type === activeViewType.value)!
))
const activeConfig = computed(() => draft.value?.view_configs?.find(
  item => item.type === activeViewType.value,
))
const activeView = computed<CharacterReferenceView | null>(() => (
  viewMap.value.get(activeViewType.value) ?? null
))
const activeTemplates = computed(() => (store.viewTemplates ?? []).filter(
  item => item.view_type === activeViewType.value,
))
const initialTemplates = computed(() => (store.viewTemplates ?? []).filter(
  item => item.view_type === initialViewType.value,
))
const selectedEngineCost = computed(() => getCharacterViewEngineCost(selectedEngine.value))
const readyCount = computed(() => draft.value?.views.filter(view => view.status === 'ready').length ?? 0)
const isInitialCustom = computed(() => initialViewType.value.startsWith('custom_'))
const availableDefinitions = computed(() => VIEW_DEFINITIONS.filter(definition => (
  WEB_CHARACTER_EXPLICIT_VIEWS_ENABLED
  || !['genitals_front', 'pelvis_back'].includes(definition.type)
)))

const viewLabel = (definition: ViewDefinition) => (
  viewMap.value.get(definition.type)?.label
  ?? draft.value?.view_configs?.find(item => item.type === definition.type)?.label
  ?? t(definition.labelKey)
)

const syncActiveForm = () => {
  viewForm.displayName = activeView.value?.label ?? viewLabel(activeDefinition.value)
  viewForm.description = activeView.value?.description ?? ''
  viewForm.prompt = activeView.value?.prompt
    || draft.value?.default_prompts?.[activeViewType.value]
    || ''
  selectedTemplateId.value = null
}

watch([activeViewType, activeView], syncActiveForm, { immediate: true })

const validateImage = (file: File) => {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    message.error(t('characters.image_type_error'))
    return false
  }
  return true
}

const beforeInitialUpload = async (file: File) => {
  if (!validateImage(file)) return false
  initialSourceKey.value = await uploadFile(file, {
    maxSizeBytes: 20 * 1024 * 1024,
    maxSizeLabel: '20MB',
  }) ?? null
  initialTemplateId.value = null
  if (initialPreview.value) URL.revokeObjectURL(initialPreview.value)
  initialPreview.value = initialSourceKey.value ? URL.createObjectURL(file) : null
  return false
}

const chooseInitialTemplate = (templateId?: string | null) => {
  initialTemplateId.value = templateId ?? null
  initialSourceKey.value = null
  if (initialPreview.value) URL.revokeObjectURL(initialPreview.value)
  initialPreview.value = (store.viewTemplates ?? []).find(item => item.id === templateId)?.preview_url ?? null
}

const createDraft = async () => {
  if (!name.value.trim() || (!initialSourceKey.value && !initialTemplateId.value)) return
  if (isInitialCustom.value && !initialViewLabel.value.trim()) {
    message.warning(t('characters.custom_label_required'))
    return
  }
  creating.value = true
  try {
    const created = await store.createDraft({
      name: name.value.trim(),
      initial_view_type: initialViewType.value,
      initial_view_label: isInitialCustom.value ? initialViewLabel.value.trim() : undefined,
      source_object_key: initialSourceKey.value ?? undefined,
      template_id: initialTemplateId.value ?? undefined,
    })
    draftId.value = created.id
    activeViewType.value = initialViewType.value
    characterForm.description = created.description ?? ''
    message.success(t('characters.draft_created'))
  } finally {
    creating.value = false
  }
}

const beforeViewUpload = async (file: File) => {
  if (!draft.value || !validateImage(file)) return false
  const objectKey = await uploadFile(file, {
    maxSizeBytes: 20 * 1024 * 1024,
    maxSizeLabel: '20MB',
  })
  if (!objectKey || !draft.value) return false
  await store.uploadView(draft.value.id, activeViewType.value, objectKey)
  if (activeConfig.value?.custom && viewForm.displayName.trim()) {
    await store.updateViewDetails(draft.value.id, activeViewType.value, {
      display_name: viewForm.displayName.trim(),
      description: viewForm.description.trim(),
    })
  }
  message.success(t('characters.view_uploaded', { view: viewForm.displayName }))
  return false
}

const applyTemplate = async () => {
  if (!draft.value || !selectedTemplateId.value) return
  applyingTemplate.value = true
  try {
    await store.applyViewTemplate(draft.value.id, activeViewType.value, selectedTemplateId.value)
    message.success(t('characters.template_applied'))
  } finally {
    applyingTemplate.value = false
  }
}

const generateView = async () => {
  if (!draft.value || !activeConfig.value?.can_generate || !viewForm.prompt.trim()) return
  generating.value = true
  try {
    await store.generateView(
      draft.value.id,
      activeViewType.value,
      viewForm.prompt.trim(),
      selectedEngine.value,
      viewForm.displayName,
    )
    message.success(t('characters.view_submitted', { view: viewForm.displayName }))
  } finally {
    generating.value = false
  }
}

const restoreDefaultPrompt = () => {
  viewForm.prompt = activeView.value?.default_prompt
    || draft.value?.default_prompts?.[activeViewType.value]
    || ''
}

const saveDescriptions = async () => {
  if (!draft.value) return
  savingDetails.value = true
  try {
    await store.rename(draft.value.id, { description: characterForm.description.trim() })
    if (activeView.value) {
      await store.updateViewDetails(draft.value.id, activeViewType.value, {
        display_name: viewForm.displayName.trim(),
        description: viewForm.description.trim(),
      })
    }
    message.success(t('characters.details_updated'))
  } finally {
    savingDetails.value = false
  }
}

const rebuildMosaic = async () => {
  if (!draft.value || readyCount.value < 1) return
  await store.saveReference(draft.value.id)
  message.success(t('characters.reference_updated'))
}

const resetWorkspace = () => {
  draftId.value = null
  name.value = ''
  initialViewType.value = 'face_front'
  initialViewLabel.value = ''
  initialSourceKey.value = null
  initialTemplateId.value = null
  if (initialPreview.value?.startsWith('blob:')) URL.revokeObjectURL(initialPreview.value)
  initialPreview.value = null
}

onMounted(() => void store.refresh())
onBeforeUnmount(() => {
  if (initialPreview.value?.startsWith('blob:')) URL.revokeObjectURL(initialPreview.value)
})
</script>

<template>
  <section class="character-workbench overflow-hidden rounded-[28px] border">
    <header class="character-workbench__hero px-5 py-5 sm:px-7">
      <div class="flex items-start gap-3">
        <div class="character-workbench__icon flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl"><Sparkles :size="22" /></div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">{{ t('characters.lab_eyebrow') }}</div>
          <h2 class="mt-1 text-xl font-bold sm:text-2xl">{{ t('characters.lab_title') }}</h2>
          <p class="mt-2 max-w-3xl text-sm leading-6">{{ t('characters.flexible_lab_description') }}</p>
        </div>
      </div>
    </header>

    <div v-if="!draft" class="grid gap-5 p-5 sm:p-7 lg:grid-cols-[300px_minmax(0,1fr)]">
      <a-upload class="character-workbench__upload" :show-upload-list="false" :before-upload="beforeInitialUpload" accept="image/png,image/jpeg,image/webp">
        <div class="character-workbench__source flex aspect-[4/5] w-full cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border border-dashed">
          <img v-if="initialPreview" :src="initialPreview" class="h-full w-full object-contain" />
          <template v-else><ImagePlus :size="34" /><span class="mt-3 text-sm font-semibold">{{ t('characters.upload_first_view') }}</span></template>
        </div>
      </a-upload>
      <div class="space-y-4">
        <label class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.name_label') }}</span><a-input v-model:value="name" size="large" :maxlength="60" /></label>
        <label class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.initial_view_type') }}</span>
          <a-select v-model:value="initialViewType" class="w-full" size="large" @change="() => { initialTemplateId = null; initialViewLabel = '' }">
            <a-select-option v-for="definition in availableDefinitions" :key="definition.type" :value="definition.type">{{ t(definition.labelKey) }}</a-select-option>
          </a-select>
        </label>
        <label v-if="isInitialCustom" class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.custom_view_name') }}</span><a-input v-model:value="initialViewLabel" :maxlength="80" /></label>
        <div v-if="initialTemplates.length" class="rounded-2xl border p-3">
          <div class="mb-2 text-sm font-semibold">{{ t('characters.choose_admin_template') }}</div>
          <a-select :value="initialTemplateId" class="w-full" allow-clear @change="chooseInitialTemplate">
            <a-select-option v-for="template in initialTemplates" :key="template.id" :value="template.id">{{ template.name }}</a-select-option>
          </a-select>
        </div>
        <p class="text-xs leading-5 opacity-65">{{ t('characters.description_after_create_hint') }}</p>
        <a-button type="primary" size="large" class="h-12 w-full rounded-2xl" :disabled="!name.trim() || (!initialSourceKey && !initialTemplateId)" :loading="creating || uploading" @click="createDraft">{{ t('characters.create_from_first_view') }}</a-button>
      </div>
    </div>

    <div v-else class="p-4 sm:p-6">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4">
        <div><div class="font-semibold">{{ draft.name }}</div><div class="mt-1 text-xs opacity-65">{{ t('characters.ready_optional_count', { count: readyCount }) }}</div></div>
        <div class="flex gap-2"><a-button size="small" @click="rebuildMosaic">{{ t('characters.rebuild_mosaic') }}</a-button><a-button size="small" @click="resetWorkspace">{{ t('characters.new_character') }}</a-button></div>
      </div>

      <div class="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <button v-for="definition in availableDefinitions" :key="definition.type" type="button" class="character-workbench__tab rounded-2xl border px-3 py-3 text-left" :class="{ 'character-workbench__tab--active': activeViewType === definition.type }" @click="activeViewType = definition.type">
          <div class="flex items-center justify-between gap-2"><span class="truncate text-sm font-semibold">{{ viewLabel(definition) }}</span><CheckCircle2 v-if="viewMap.get(definition.type)?.status === 'ready'" :size="16" class="text-emerald-400" /><RefreshCw v-else-if="viewMap.get(definition.type)?.status === 'pending'" :size="16" class="animate-spin text-cyan-400" /></div>
        </button>
      </div>

      <div class="grid gap-5 lg:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.1fr)]">
        <div class="character-workbench__preview flex min-h-[260px] items-center justify-center overflow-hidden rounded-3xl border sm:min-h-[360px]">
          <img v-if="activeView?.preview_url" :src="activeView.preview_url" class="max-h-[560px] w-full object-contain" />
          <div v-else class="text-center opacity-60"><ImagePlus :size="36" class="mx-auto" /><div class="mt-3 text-sm">{{ t('characters.view_optional_empty') }}</div></div>
        </div>
        <div class="space-y-4">
          <section data-testid="character-view-details-section" class="character-workbench__section rounded-3xl border p-4 sm:p-5">
            <header class="mb-5 flex items-start gap-3">
              <span class="character-workbench__step flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold">1</span>
              <div>
                <h3 class="text-base font-bold">{{ t('characters.details_section_title') }}</h3>
                <p class="mt-1 text-xs leading-5 opacity-60">{{ t('characters.details_section_hint') }}</p>
              </div>
            </header>
            <div class="space-y-4">
              <label class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.character_description') }}</span><a-textarea v-model:value="characterForm.description" :maxlength="500" :auto-size="{ minRows: 2, maxRows: 5 }" /></label>
              <label class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.view_display_name') }}</span><a-input v-model:value="viewForm.displayName" :maxlength="80" /></label>
              <label class="block"><span class="mb-2 block text-sm font-semibold">{{ t('characters.view_description') }}</span><a-textarea v-model:value="viewForm.description" :maxlength="500" :auto-size="{ minRows: 2, maxRows: 5 }" /></label>
            </div>
            <div class="mt-5 flex justify-end">
              <a-button class="w-full sm:w-auto" :loading="savingDetails" @click="saveDescriptions">{{ t('characters.save_descriptions') }}</a-button>
            </div>
          </section>

          <section data-testid="character-view-generation-section" class="character-workbench__section rounded-3xl border p-4 sm:p-5">
            <header class="mb-5 flex items-start gap-3">
              <span class="character-workbench__step flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold">2</span>
              <div>
                <h3 class="text-base font-bold">{{ t('characters.generation_section_title') }}</h3>
                <p class="mt-1 text-xs leading-5 opacity-60">{{ t('characters.generation_section_hint') }}</p>
              </div>
            </header>

            <template v-if="activeConfig?.can_generate">
              <label class="block">
                <span class="mb-2 flex items-center justify-between gap-3 text-sm font-semibold">
                  {{ t('characters.view_prompt_label') }}
                  <button type="button" class="character-workbench__text-action text-xs font-semibold" @click="restoreDefaultPrompt">{{ t('characters.restore_default') }}</button>
                </span>
                <a-textarea v-model:value="viewForm.prompt" :maxlength="1200" :auto-size="{ minRows: 3, maxRows: 7 }" />
              </label>
              <div class="mt-5">
                <div class="mb-2 text-sm font-semibold">{{ t('characters.engine_label') }}</div>
                <a-radio-group v-model:value="selectedEngine" button-style="solid" class="character-workbench__engine-grid">
                  <a-radio-button v-for="option in CHARACTER_VIEW_ENGINE_OPTIONS" :key="option.value" :value="option.value" data-testid="character-engine-option">
                    <span class="flex w-full items-center justify-between gap-3">
                      <span class="truncate font-semibold">{{ t(option.labelKey) }}</span>
                      <span class="character-workbench__cost shrink-0 rounded-full px-2 py-0.5 text-xs">{{ option.cost }} {{ t('app.credits') }}</span>
                    </span>
                  </a-radio-button>
                </a-radio-group>
              </div>
            </template>

            <div v-if="activeConfig?.has_templates" class="character-workbench__template mt-5 rounded-2xl border p-3">
              <div class="mb-2 text-sm font-semibold">{{ t('characters.choose_admin_template') }}</div>
              <div class="flex flex-col gap-2 sm:flex-row"><a-select v-model:value="selectedTemplateId" class="min-w-0 flex-1" allow-clear><a-select-option v-for="template in activeTemplates" :key="template.id" :value="template.id">{{ template.name }}</a-select-option></a-select><a-button :disabled="!selectedTemplateId" :loading="applyingTemplate" @click="applyTemplate">{{ t('characters.apply_template') }}</a-button></div>
            </div>

            <div class="mt-5 border-t pt-4">
              <p class="mb-3 text-xs leading-5 opacity-60">{{ t('characters.upload_view_hint') }}</p>
              <div class="grid gap-2" :class="activeConfig?.can_generate ? 'sm:grid-cols-2' : ''">
                <a-upload class="character-workbench__upload-action" :show-upload-list="false" :before-upload="beforeViewUpload" accept="image/png,image/jpeg,image/webp">
                  <a-button class="h-11 w-full" :loading="uploading">{{ activeView ? t('characters.replace_view_upload') : t('characters.upload_view') }}</a-button>
                </a-upload>
                <a-button v-if="activeConfig?.can_generate" type="primary" class="h-11 w-full" :disabled="!viewForm.prompt.trim() || activeView?.status === 'pending'" :loading="generating || activeView?.status === 'pending'" @click="generateView">{{ t('characters.generate_view') }} · {{ selectedEngineCost }} {{ t('app.credits') }}</a-button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.character-workbench { color: var(--theme-text-primary); background: var(--theme-card-bg); border-color: var(--theme-border); }
.character-workbench__hero { background: radial-gradient(circle at 90% 0%, rgba(34, 211, 238, 0.15), transparent 35%), var(--theme-card-bg); border-bottom: 1px solid var(--theme-border); }
.character-workbench__icon { color: #67e8f9; background: rgba(34, 211, 238, 0.13); border: 1px solid rgba(34, 211, 238, 0.32); }
.character-workbench__source, .character-workbench__preview, .character-workbench__tab { background: var(--theme-panel-strong-bg); border-color: var(--theme-border); }
.character-workbench__tab--active { border-color: var(--theme-tab-active-border); box-shadow: var(--theme-tab-active-shadow); }
.character-workbench__section { background: var(--theme-panel-strong-bg); border-color: var(--theme-border); }
.character-workbench__step { color: var(--theme-tab-active-text); background: var(--theme-tab-active-bg); border: 1px solid var(--theme-tab-active-border); }
.character-workbench__text-action { color: var(--theme-tab-active-text); }
.character-workbench__template { border-color: var(--theme-border); background: var(--theme-card-bg); }
.character-workbench__engine-grid { display: grid; width: 100%; gap: 0.5rem; }
.character-workbench__engine-grid :deep(.ant-radio-button-wrapper) { display: flex; width: 100%; height: auto; min-height: 44px; align-items: center; border: 1px solid var(--theme-border); border-radius: 14px; padding: 0.65rem 0.75rem; background: var(--theme-card-bg); color: var(--theme-text-primary); box-shadow: none; }
.character-workbench__engine-grid :deep(.ant-radio-button-wrapper::before) { display: none; }
.character-workbench__engine-grid :deep(.ant-radio-button-wrapper-checked) { border-color: var(--theme-tab-active-border); background: var(--theme-tab-active-bg); color: var(--theme-text-primary); box-shadow: var(--theme-tab-active-shadow); }
.character-workbench__cost { background: rgba(14, 165, 233, 0.12); color: var(--theme-tab-active-text); }
.character-workbench__upload-action { display: block; width: 100%; }
.character-workbench__upload-action :deep(.ant-upload) { display: block; width: 100%; }

@media (min-width: 640px) {
  .character-workbench__engine-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
