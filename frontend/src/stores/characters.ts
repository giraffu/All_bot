import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  buildCharacter,
  deleteCharacter,
  fetchCharacters,
  updateCharacter,
  type CharacterReference,
} from '@/api/characters'

export const useCharactersStore = defineStore('characters', () => {
  const items = ref<CharacterReference[]>([])
  const loading = ref(false)
  const readyItems = computed(() => items.value.filter(item => item.status === 'ready'))

  const refresh = async () => {
    loading.value = true
    try {
      items.value = await fetchCharacters()
    } finally {
      loading.value = false
    }
  }

  const create = async (payload: { name: string; description?: string; source_object_key: string }) => {
    const result = await buildCharacter(payload)
    await refresh()
    return result
  }

  const rename = async (id: string, payload: { name?: string; description?: string }) => {
    await updateCharacter(id, payload)
    await refresh()
  }

  const remove = async (id: string) => {
    await deleteCharacter(id)
    items.value = items.value.filter(item => item.id !== id)
  }

  return { items, readyItems, loading, refresh, create, rename, remove }
})
