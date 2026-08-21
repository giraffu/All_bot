import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchCharacterBatchCapacity: vi.fn(),
  fetchCharacters: vi.fn(),
  generateCharacterView: vi.fn(),
  uploadCharacterView: vi.fn(),
  confirmCharacterReference: vi.fn(),
}))
const addTask = vi.hoisted(() => vi.fn())
const settleExternalTask = vi.hoisted(() => vi.fn())

vi.mock('@/api/characters', () => ({
  buildCharacter: vi.fn(),
  confirmCharacterReference: apiMocks.confirmCharacterReference,
  createCharacterDraft: vi.fn(),
  deleteCharacter: vi.fn(),
  fetchCharacterBatchCapacity: apiMocks.fetchCharacterBatchCapacity,
  fetchCharacters: apiMocks.fetchCharacters,
  generateCharacterView: apiMocks.generateCharacterView,
  uploadCharacterView: apiMocks.uploadCharacterView,
  saveCharacterReference: vi.fn(),
  updateCharacter: vi.fn(),
}))

vi.mock('@/stores/tasks', () => ({
  useTasksStore: () => ({ addTask, settleExternalTask }),
}))

import { createPinia, setActivePinia } from 'pinia'

import { useCharactersStore } from './characters'

describe('characters store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.fetchCharacters.mockResolvedValue([])
    apiMocks.fetchCharacterBatchCapacity.mockResolvedValue({
      limit: 5,
      active: 2,
      available: 3,
    })
  })

  it('reads live batch capacity through the characters store seam', async () => {
    const store = useCharactersStore()

    await expect(store.getBatchCapacity()).resolves.toEqual({
      limit: 5,
      active: 2,
      available: 3,
    })
  })

  it('persists the one-time adult, rights, and missing-gender confirmation', async () => {
    apiMocks.confirmCharacterReference.mockResolvedValue({
      id: 'character-1',
      adult_confirmed: true,
      usage_rights_confirmed: true,
      views: [],
    })
    const store = useCharactersStore()

    await store.confirmIdentity('character-1', { gender: 'female' })

    expect(apiMocks.confirmCharacterReference).toHaveBeenCalledWith('character-1', {
      prompt_profile: { gender: 'female' },
      adult_confirmed: true,
      usage_rights_confirmed: true,
    })
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
      'body_side',
      'side body',
      'free_edit_v2_5',
      '全身侧面图',
    )

    expect(apiMocks.generateCharacterView).toHaveBeenCalledWith(
      'character-1',
      'body_side',
      'side body',
      'free_edit_v2_5',
    )
    expect(addTask).toHaveBeenCalledWith(
      'character-view-task-1',
      'free_edit_v2_5',
      '人物参考图 · 全身侧面图',
    )
  })

  it('uploads a view without registering a floating generation task', async () => {
    apiMocks.uploadCharacterView.mockResolvedValue({
      type: 'face_front',
      status: 'ready',
      preview_url: 'https://example.com/front.png',
    })

    const store = useCharactersStore()
    await store.uploadView(
      'character-1',
      'face_front',
      'web_uploads/123/front.png',
    )

    expect(apiMocks.uploadCharacterView).toHaveBeenCalledWith(
      'character-1',
      'face_front',
      'web_uploads/123/front.png',
    )
    expect(addTask).not.toHaveBeenCalled()
  })

  it('settles floating tasks from persisted character view terminal states', async () => {
    apiMocks.fetchCharacters.mockResolvedValue([
      {
        id: 'character-1',
        views: [
          {
            type: 'face_front',
            label: '正脸图',
            task_id: 'ready-view-task',
            status: 'ready',
            preview_url: 'https://example.com/ready.png',
          },
          {
            type: 'body_back',
            label: '全身背面图',
            task_id: 'failed-view-task',
            status: 'failed',
            preview_url: null,
          },
          {
            type: 'body_side',
            label: '全身侧面图',
            task_id: 'pending-view-task',
            status: 'pending',
            preview_url: null,
          },
        ],
      },
    ])

    const store = useCharactersStore()
    await store.refresh()

    expect(settleExternalTask).toHaveBeenCalledWith('ready-view-task', {
      status: 'success',
      resultUrl: 'https://example.com/ready.png',
    })
    expect(settleExternalTask).toHaveBeenCalledWith('failed-view-task', {
      status: 'failed',
      error: '人物子图生成失败',
    })
    expect(settleExternalTask).not.toHaveBeenCalledWith(
      'pending-view-task',
      expect.anything(),
    )
  })
})
