<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import { useUpload } from '@/composables/useUpload'
import { useCharactersStore } from '@/stores/characters'

const { t } = useI18n()
const store = useCharactersStore()
const { uploading, uploadFile } = useUpload()
const name = ref('')
const description = ref('')
const sourceKey = ref<string | null>(null)
const sourcePreview = ref<string | null>(null)
const submitting = ref(false)
const editingId = ref<string | null>(null)
const editingName = ref('')
let refreshTimer: ReturnType<typeof setTimeout> | null = null
let stopped = false

const refreshUntilSettled = async () => {
  try {
    await store.refresh()
  } finally {
    if (!stopped && store.items.some(character => character.status === 'pending')) {
      refreshTimer = setTimeout(() => void refreshUntilSettled(), 5000)
    }
  }
}

const ensureRefreshPolling = () => {
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = null
  void refreshUntilSettled()
}

onMounted(ensureRefreshPolling)
onUnmounted(() => {
  stopped = true
  if (refreshTimer) clearTimeout(refreshTimer)
  if (sourcePreview.value) URL.revokeObjectURL(sourcePreview.value)
})

const beforeUpload = async (file: File) => {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    message.error(t('characters.image_type_error'))
    return false
  }
  sourceKey.value = await uploadFile(file, { maxSizeBytes: 20 * 1024 * 1024, maxSizeLabel: '20MB' })
  if (sourcePreview.value) URL.revokeObjectURL(sourcePreview.value)
  sourcePreview.value = sourceKey.value ? URL.createObjectURL(file) : null
  return false
}

const submit = async () => {
  if (!name.value.trim() || !sourceKey.value) return
  const characterDescription = description.value.trim()
  if (!characterDescription) {
    message.error(t('characters.description_required'))
    return
  }
  submitting.value = true
  try {
    await store.create({
      name: name.value.trim(),
      description: characterDescription,
      source_object_key: sourceKey.value,
    })
    name.value = ''
    description.value = ''
    sourceKey.value = null
    sourcePreview.value = null
    ensureRefreshPolling()
    message.success(t('characters.build_submitted'))
  } finally {
    submitting.value = false
  }
}

const remove = (id: string) => Modal.confirm({
  title: t('characters.delete_confirm'),
  onOk: () => store.remove(id),
})

const startRename = (id: string, currentName: string) => {
  editingId.value = id
  editingName.value = currentName
}

const saveRename = async (id: string) => {
  const nextName = editingName.value.trim()
  if (!nextName) return
  await store.rename(id, { name: nextName })
  editingId.value = null
}

const retry = async (character: (typeof store.items)[number]) => {
  if (!character.description?.trim()) {
    message.error(t('characters.description_required'))
    return
  }
  await store.create({
    name: character.name,
    description: character.description.trim(),
    source_object_key: character.source_object_key,
  })
  ensureRefreshPolling()
  message.success(t('characters.build_submitted'))
}
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-5" data-testid="characters-page">
    <section class="rounded-3xl border p-5">
      <h1 class="text-xl font-bold">{{ t('characters.title') }}</h1>
      <p class="mt-2 text-sm opacity-70">{{ t('characters.description') }}</p>
      <div class="mt-4 grid gap-4 md:grid-cols-[220px_1fr]">
        <a-upload class="character-source-upload" :show-upload-list="false" :before-upload="beforeUpload" accept="image/png,image/jpeg,image/webp">
          <div class="flex h-48 w-full cursor-pointer items-center justify-center overflow-hidden rounded-2xl border border-dashed md:w-[220px]">
            <img v-if="sourcePreview" :src="sourcePreview" class="h-full w-full object-cover" />
            <span v-else>{{ t('characters.upload_source') }}</span>
          </div>
        </a-upload>
        <div class="space-y-3">
          <a-input v-model:value="name" :maxlength="60" :placeholder="t('characters.name_placeholder')" />
          <a-textarea v-model:value="description" :maxlength="500" :rows="4" :placeholder="t('characters.description_placeholder')" />
          <a-button type="primary" :disabled="!name.trim() || !description.trim() || !sourceKey" :loading="submitting || uploading" @click="submit">
            {{ t('characters.build_button') }} · 18 {{ t('app.credits') }}
          </a-button>
        </div>
      </div>
    </section>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <article v-for="character in store.items" :key="character.id" class="overflow-hidden rounded-3xl border p-4">
        <div class="aspect-[12/7] overflow-hidden rounded-2xl bg-black">
          <img v-if="character.preview_url" :src="character.preview_url" class="h-full w-full object-contain" />
          <div v-else class="flex h-full items-center justify-center text-sm opacity-70">{{ t(`characters.status_${character.status}`) }}</div>
        </div>
        <div class="mt-3 flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div v-if="editingId === character.id" class="flex gap-2">
              <a-input v-model:value="editingName" :maxlength="60" size="small" @press-enter="saveRename(character.id)" />
              <a-button size="small" type="primary" @click="saveRename(character.id)">{{ t('characters.save') }}</a-button>
            </div>
            <div v-else class="truncate font-semibold">{{ character.name }}</div>
            <div class="text-xs opacity-65">{{ t(`characters.status_${character.status}`) }}</div>
          </div>
          <div class="flex shrink-0 gap-1">
            <a-button v-if="character.status === 'failed'" size="small" @click="retry(character)">{{ t('characters.retry') }}</a-button>
            <a-button size="small" @click="startRename(character.id, character.name)">{{ t('characters.rename') }}</a-button>
            <a-button danger size="small" :disabled="character.status === 'pending'" @click="remove(character.id)">{{ t('characters.delete') }}</a-button>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.character-source-upload {
  display: block;
  width: 100%;
}

.character-source-upload :deep(.ant-upload-select) {
  display: block;
  width: 100%;
}
</style>
