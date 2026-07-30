import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  buildCharacter,
  createCharacterDraft,
  deleteCharacter,
  fetchCharacterBatchCapacity,
  fetchCharacters,
  generateCharacterView,
  saveCharacterReference,
  updateCharacter,
  type CharacterReference,
  type CharacterViewEngine,
  type CharacterViewType,
} from '@/api/characters'
import { useTasksStore } from '@/stores/tasks'

export const useCharactersStore = defineStore('characters', () => {
  const tasksStore = useTasksStore()
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

  const getBatchCapacity = () => fetchCharacterBatchCapacity()

  const generateView = async (
    id: string,
    viewType: CharacterViewType,
    prompt: string,
    engine: CharacterViewEngine = 'free_edit_v2_5',
    viewLabel: string = viewType,
    registerFloatingTask = true,
  ) => {
    const result = await generateCharacterView(id, viewType, prompt, engine)
    if (registerFloatingTask) {
      tasksStore.addTask(
        result.task_id,
        result.task_type,
        `人物参考图 · ${viewLabel}`,
      )
    }
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
    getBatchCapacity,
    generateView,
    saveReference,
    rename,
    remove,
  }
})
