<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useCharactersStore } from '@/stores/characters'

type OfficialReferenceAsset = {
  id: string
  name: string
  description: string
}

const props = withDefaults(defineProps<{
  modelValue: string[]
  enabled?: boolean
  environmentSource?: 'official' | 'upload'
  environmentId?: string
  canUploadEnvironment?: boolean
  beforeUploadEnvironment?: (file: File) => boolean | Promise<boolean>
}>(), {
  enabled: true,
  environmentSource: 'upload',
  environmentId: '',
  canUploadEnvironment: false,
})
const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  'update:enabled': [value: boolean]
  'update:environmentSource': [value: 'official' | 'upload']
  'update:environmentId': [value: string]
}>()
const store = useCharactersStore()
const { t } = useI18n()
const maxCharacters = 2
const officialCharacters = ref<OfficialReferenceAsset[]>([])
const officialEnvironments = ref<OfficialReferenceAsset[]>([])
const selectedCharacters = computed(() => props.modelValue
  .map((ref) => {
    const [source, id] = ref.includes(':') ? ref.split(':', 2) : ['private', ref]
    return source === 'official'
      ? officialCharacters.value.find(character => character.id === id)
      : store.readyItems.find(character => character.id === id)
  })
  .filter(character => Boolean(character)))

const updateCharacters = (value: unknown) => {
  const ids = Array.isArray(value)
    ? value.map(String).slice(0, maxCharacters)
    : value
      ? [String(value)]
      : []
  emit('update:modelValue', ids)
}

onMounted(async () => {
  const { fetchOfficialCharacters, fetchOfficialEnvironments } = await import('@/api/referenceAssets')
  await Promise.allSettled([
    store.refresh(),
    fetchOfficialCharacters().then(value => { officialCharacters.value = value }),
    fetchOfficialEnvironments().then(value => { officialEnvironments.value = value }),
  ])
})
</script>

<template>
  <section class="rounded-2xl border p-4" data-testid="ltx-t2v-character-selector">
    <div class="mb-3 flex items-center justify-between gap-3">
      <div class="text-sm font-semibold">使用角色与环境参考</div>
      <a-switch :checked="enabled" @update:checked="emit('update:enabled', Boolean($event))" />
    </div>
    <template v-if="enabled">
    <div class="mb-2 text-sm font-semibold">请选择恰好两个角色</div>
    <a-select
      :value="modelValue"
      mode="multiple"
      allow-clear
      class="w-full"
      :loading="store.loading"
      :placeholder="t('characters.selector_placeholder')"
      @update:value="updateCharacters"
      @clear="emit('update:modelValue', [])"
    >
      <a-select-opt-group label="我的角色">
        <a-select-option v-for="character in store.readyItems" :key="`private:${character.id}`" :value="`private:${character.id}`">{{ character.name }}</a-select-option>
      </a-select-opt-group>
      <a-select-opt-group label="官方角色">
        <a-select-option v-for="character in officialCharacters" :key="`official:${character.id}`" :value="`official:${character.id}`">{{ character.name }}</a-select-option>
      </a-select-opt-group>
    </a-select>
    <div v-if="selectedCharacters.length" class="mt-3 grid gap-2">
      <div
        v-for="(character, index) in selectedCharacters"
        :key="character!.id"
        class="rounded-xl border px-3 py-2 text-xs"
      >
        <span class="font-semibold">{{ t('characters.msr_image_label', { index: index + 1 }) }}</span>
        <span class="ml-2">{{ character!.name }}</span>
        <div class="mt-1 opacity-70">{{ character!.description }}</div>
      </div>
    </div>
    <div class="mt-2 text-xs opacity-70">
      {{ modelValue.length === 2
        ? t('characters.msr_hint')
        : modelValue.length === 1
          ? t('characters.msr_requires_two_hint')
          : t('characters.t2v_hint') }}
    </div>
    <div class="mt-4 border-t pt-4">
      <div class="mb-2 text-sm font-semibold">环境图（必填，单张即可）</div>
      <a-radio-group :value="environmentSource" @update:value="emit('update:environmentSource', $event)">
        <a-radio-button value="official">官方环境</a-radio-button>
        <a-radio-button value="upload">上传环境</a-radio-button>
      </a-radio-group>
      <a-select v-if="environmentSource === 'official'" class="mt-3 w-full" :value="environmentId"
        placeholder="选择官方环境" @update:value="emit('update:environmentId', String($event || ''))">
        <a-select-option v-for="environment in officialEnvironments" :key="environment.id" :value="environment.id">
          {{ environment.name }}
        </a-select-option>
      </a-select>
      <div v-else class="mt-3">
        <a-upload
          v-if="canUploadEnvironment && beforeUploadEnvironment"
          accept="image/png,image/jpeg,image/webp"
          :show-upload-list="false"
          :before-upload="beforeUploadEnvironment"
        >
          <a-button type="primary" ghost>上传环境图</a-button>
        </a-upload>
        <div class="mt-2 text-xs opacity-70">上传一张 PNG、JPEG 或 WebP 环境图；不需要多视角。</div>
      </div>
    </div>
    </template>
    <div v-else class="text-xs opacity-70">关闭后使用纯文生视频，不会携带任何角色或环境素材。</div>
  </section>
</template>
