import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchCharacters: vi.fn(),
  generateCharacterView: vi.fn(),
}))
const addTask = vi.hoisted(() => vi.fn())

vi.mock('@/api/characters', () => ({
  buildCharacter: vi.fn(),
  createCharacterDraft: vi.fn(),
  deleteCharacter: vi.fn(),
  fetchCharacters: apiMocks.fetchCharacters,
  generateCharacterView: apiMocks.generateCharacterView,
  saveCharacterReference: vi.fn(),
  updateCharacter: vi.fn(),
}))

vi.mock('@/stores/tasks', () => ({
  useTasksStore: () => ({ addTask }),
}))

import { createPinia, setActivePinia } from 'pinia'

import { useCharactersStore } from './characters'

describe('characters store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.fetchCharacters.mockResolvedValue([])
  })

  it('submits the selected free-edit engine and registers a floating task', async () => {
    apiMocks.generateCharacterView.mockResolvedValue({
      task_id: 'character-view-task-1',
      task_type: 'free_edit_v2_5',
      status: 'pending',
    })

    const store = useCharactersStore()
    await store.generateView(
      'character-1',
      'face_side',
      'side portrait',
      'free_edit_v2_5',
      '侧脸图',
    )

    expect(apiMocks.generateCharacterView).toHaveBeenCalledWith(
      'character-1',
      'face_side',
      'side portrait',
      'free_edit_v2_5',
    )
    expect(addTask).toHaveBeenCalledWith(
      'character-view-task-1',
      'free_edit_v2_5',
      '人物参考图 · 侧脸图',
    )
  })
})
