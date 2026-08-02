<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { getRuntimeFlag } from '@/config/runtime'
import { useCharactersStore } from '@/stores/characters'

const props = defineProps<{
  modelValue: string[]
  sulphurStrength: number
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  'update:sulphurStrength': [value: number]
}>()
const store = useCharactersStore()
const { t } = useI18n()
const msrEnabled = getRuntimeFlag('enable_ltx_t2v_msr', false)
const maxCharacters = msrEnabled ? 4 : 1
const selectedCharacters = computed(() => props.modelValue
  .map(id => store.readyItems.find(character => character.id === id))
  .filter(character => Boolean(character)))

const updateCharacters = (value: unknown) => {
  const ids = Array.isArray(value)
    ? value.map(String).slice(0, maxCharacters)
    : value
      ? [String(value)]
      : []
  emit('update:modelValue', ids)
}

onMounted(() => void store.refresh())
</script>

<template>
  <section class="rounded-2xl border p-4" data-testid="ltx-t2v-character-selector">
    <div class="mb-2 text-sm font-semibold">{{ t('characters.selector_title') }}</div>
    <a-select
      :value="msrEnabled ? modelValue : modelValue[0]"
      :mode="msrEnabled ? 'multiple' : undefined"
      allow-clear
      class="w-full"
      :loading="store.loading"
      :placeholder="t('characters.selector_placeholder')"
      @update:value="updateCharacters"
      @clear="emit('update:modelValue', [])"
    >
      <a-select-option v-for="character in store.readyItems" :key="character.id" :value="character.id">
        {{ character.name }}
      </a-select-option>
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
    <div v-if="msrEnabled && modelValue.length >= 2" class="mt-4">
      <div class="mb-2 flex items-center justify-between text-xs">
        <span>{{ t('characters.sulphur_strength') }}</span>
        <span>{{ sulphurStrength.toFixed(2) }}</span>
      </div>
      <a-slider
        :value="sulphurStrength"
        :min="0"
        :max="1"
        :step="0.05"
        @update:value="emit('update:sulphurStrength', Number($event))"
      />
      <div class="text-xs opacity-70">{{ t('characters.sulphur_hint') }}</div>
    </div>
    <div class="mt-2 text-xs opacity-70">
      {{ modelValue.length >= 2
        ? t('characters.msr_hint')
        : modelValue.length === 1
          ? t('characters.ic_locked_hint')
          : t('characters.t2v_hint') }}
    </div>
  </section>
</template>
