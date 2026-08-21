import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  buildCharacter,
  confirmCharacterReference,
  createCharacterDraft,
  deleteCharacter,
  fetchCharacterBatchCapacity,
  fetchCharacters,
  generateCharacterView,
  saveCharacterReference,
  uploadCharacterView,
  updateCharacter,
  type CharacterReference,
  type CharacterPromptProfile,
  type CharacterViewEngine,
  type CharacterViewType,
} from '@/api/characters'
import { runCharacterViewBatch } from '@/features/characters/characterBatchGeneration'
import i18n from '@/i18n'
import { useTasksStore } from '@/stores/tasks'

export const useCharactersStore = defineStore('characters', () => {
  const tasksStore = useTasksStore()
  const items = ref<CharacterReference[]>([])
  const loading = ref(false)
  const batchRuns = ref<Record<string, {
    running: boolean
    submitted: number
    total: number
    failed: number
    token: number
  }>>({})
  let refreshTimer: ReturnType<typeof setTimeout> | null = null
  let nextBatchToken = 0
  const readyItems = computed(() => items.value.filter(item => item.status === 'ready' && item.moderation_status !== 'disabled'))

  const reconcileViewTaskSessions = (characters: CharacterReference[]) => {
    characters.forEach(character => {
      character.views.forEach(view => {
        if (!view.task_id) return
        if (view.status === 'ready') {
          tasksStore.settleExternalTask(view.task_id, {
            status: 'success',
            resultUrl: view.preview_url ?? undefined,
          })
        } else if (view.status === 'failed') {
          tasksStore.settleExternalTask(view.task_id, {
            status: 'failed',
            error: i18n.global.t('characters.view_generation_failed'),
          })
        }
      })
    })
  }

  const refresh = async () => {
    loading.value = true
    try {
      items.value = await fetchCharacters()
      reconcileViewTaskSessions(items.value)
    } finally {
      loading.value = false
      scheduleBackgroundRefresh()
    }
  }

  const hasBackgroundWork = () => (
    items.value.some(character => character.views.some(view => view.status === 'pending'))
    || Object.values(batchRuns.value).some(run => run.running)
  )

  const scheduleBackgroundRefresh = (delay = 4000) => {
    if (refreshTimer) clearTimeout(refreshTimer)
    refreshTimer = null
    if (!hasBackgroundWork()) return
    refreshTimer = setTimeout(() => void refresh(), delay)
  }

  const create = async (payload: { name: string; description: string; source_object_key: string; prompt_profile: CharacterPromptProfile; adult_confirmed: true; usage_rights_confirmed: true }) => {
    const result = await buildCharacter(payload)
    await refresh()
    return result
  }

  const createDraft = async (payload: { name: string; description: string; source_object_key: string; prompt_profile: CharacterPromptProfile; adult_confirmed: true; usage_rights_confirmed: true }) => {
    const result = await createCharacterDraft(payload)
    items.value = [result, ...items.value.filter(item => item.id !== result.id)]
    scheduleBackgroundRefresh()
    return result
  }

  const confirmIdentity = async (id: string, promptProfile?: CharacterPromptProfile) => {
    const result = await confirmCharacterReference(id, {
      prompt_profile: promptProfile,
      adult_confirmed: true,
      usage_rights_confirmed: true,
    })
    items.value = items.value.map(item => item.id === id ? result : item)
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
    refreshAfterSubmit = true,
  ) => {
    const result = await generateCharacterView(id, viewType, prompt, engine)
    if (registerFloatingTask) {
      tasksStore.addTask(
        result.task_id,
        result.task_type,
        `人物参考图 · ${viewLabel}`,
      )
    }
    if (refreshAfterSubmit) await refresh()
    else scheduleBackgroundRefresh(2000)
    return result
  }

  const isConcurrencyLimitError = (error: unknown) => {
    const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
    return response?.status === 429
      && typeof response.data?.detail === 'string'
      && response.data.detail.includes('正在处理中')
  }

  const generateMissingViews = async (
    id: string,
    views: Array<{ type: CharacterViewType; prompt: string; label: string }>,
    engine: CharacterViewEngine,
  ) => {
    if (batchRuns.value[id]?.running || views.length === 0) return null
    const token = ++nextBatchToken
    batchRuns.value[id] = {
      running: true,
      submitted: 0,
      total: views.length,
      failed: 0,
      token,
    }
    scheduleBackgroundRefresh(1000)
    const specs = new Map(views.map(view => [view.type, view]))
    try {
      const result = await runCharacterViewBatch({
        viewTypes: views.map(view => view.type),
        getCapacity: getBatchCapacity,
        submit: async (viewType) => {
          const spec = specs.get(viewType)
          if (!spec) throw new Error(`Missing character view spec: ${viewType}`)
          await generateView(
            id,
            viewType,
            spec.prompt,
            engine,
            spec.label,
            true,
            false,
          )
        },
        waitForCapacity: async () => {
          await new Promise(resolve => setTimeout(resolve, 4000))
          await refresh()
        },
        isActive: () => batchRuns.value[id]?.token === token,
        shouldRetry: isConcurrencyLimitError,
        onProgress: ({ submitted }) => {
          const run = batchRuns.value[id]
          if (run?.token === token) run.submitted = submitted
        },
      })
      const run = batchRuns.value[id]
      if (run?.token === token) {
        run.submitted = result.submitted
        run.failed = result.failed
        run.running = false
      }
      await refresh()
      return result
    } finally {
      const run = batchRuns.value[id]
      if (run?.token === token) run.running = false
      scheduleBackgroundRefresh()
    }
  }

  const saveReference = async (id: string) => {
    const result = await saveCharacterReference(id)
    items.value = items.value.map(item => item.id === id ? result : item)
    return result
  }

  const uploadView = async (
    id: string,
    viewType: CharacterViewType,
    sourceObjectKey: string,
  ) => {
    const result = await uploadCharacterView(id, viewType, sourceObjectKey)
    await refresh()
    return result
  }

  const rename = async (id: string, payload: { name?: string; description?: string; prompt_profile?: CharacterPromptProfile }) => {
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
    batchRuns,
    refresh,
    create,
    createDraft,
    confirmIdentity,
    getBatchCapacity,
    generateView,
    generateMissingViews,
    uploadView,
    saveReference,
    rename,
    remove,
  }
})
