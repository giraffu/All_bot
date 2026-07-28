import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  buildCharacter,
  createCharacterDraft,
  deleteCharacter,
  fetchCharacters,
  generateCharacterView,
  saveCharacterReference,
  updateCharacter,
  type CharacterReference,
  type CharacterViewType,
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

  const createDraft = async (payload: { name: string; description?: string; source_object_key: string }) => {
    const result = await createCharacterDraft(payload)
    items.value = [result, ...items.value.filter(item => item.id !== result.id)]
    return result
  }

  const generateView = async (
    id: string,
    viewType: CharacterViewType,
    prompt: string,
  ) => {
    const result = await generateCharacterView(id, viewType, prompt)
    await refresh()
    return result
  }

  const saveReference = async (id: string) => {
    const result = await saveCharacterReference(id)
    items.value = items.value.map(item => item.id === id ? result : item)
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

  return {
    items,
    readyItems,
    loading,
    refresh,
    create,
    createDraft,
    generateView,
    saveReference,
    rename,
    remove,
  }
})
