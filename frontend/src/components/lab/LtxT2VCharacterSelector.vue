<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { useCharactersStore } from '@/stores/characters'

defineProps<{ modelValue: string | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()
const store = useCharactersStore()
const { t } = useI18n()

onMounted(() => void store.refresh())
</script>

<template>
  <section class="rounded-2xl border p-4" data-testid="ltx-t2v-character-selector">
    <div class="mb-2 text-sm font-semibold">{{ t('characters.selector_title') }}</div>
    <a-select
      :value="modelValue || undefined"
      allow-clear
      class="w-full"
      :loading="store.loading"
      :placeholder="t('characters.selector_placeholder')"
      @update:value="emit('update:modelValue', $event ? String($event) : null)"
      @clear="emit('update:modelValue', null)"
    >
      <a-select-option v-for="character in store.readyItems" :key="character.id" :value="character.id">
        {{ character.name }}
      </a-select-option>
    </a-select>
    <div class="mt-2 text-xs opacity-70">
      {{ modelValue ? t('characters.ic_locked_hint') : t('characters.t2v_hint') }}
    </div>
  </section>
</template>
