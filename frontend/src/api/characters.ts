import api from './index'

export type CharacterReference = {
  id: string
  name: string
  description: string | null
  status: 'draft' | 'pending' | 'ready' | 'failed'
  moderation_status: 'active' | 'disabled'
  moderation_reason: string | null
  task_id: string | null
  source_object_key: string
  sheet_object_key: string | null
  preview_url: string | null
  prompt_profile: CharacterPromptProfile | null
  default_prompts: Record<CharacterViewType, string>
  views: CharacterReferenceView[]
}

export type CharacterPromptProfile = {
  gender: 'female' | 'male'
  breast_size?: 'large' | 'natural' | 'flat'
  pubic_hair?: 'full' | 'natural' | 'none'
  skin_tone?: 'fair' | 'asian_yellow' | 'asian_tan'
}

export type CharacterReferenceView = {
  type: CharacterViewType
  label: string
  prompt: string
  default_prompt: string
  status: 'pending' | 'ready' | 'failed'
  task_id: string | null
  object_key: string | null
  preview_url: string | null
}

export type CharacterViewType =
  | 'face_front'
  | 'body_front'
  | 'body_side'
  | 'body_back'

export type CharacterViewEngine =
  | 'free_edit'
  | 'free_edit_v2_5'
  | 'free_edit_v3'

export type CharacterBatchCapacity = {
  limit: number
  active: number
  available: number
}

export const fetchCharacters = async (): Promise<CharacterReference[]> => (
  await api.get('/characters')
).data

export const fetchCharacterBatchCapacity = async (): Promise<CharacterBatchCapacity> => (
  await api.get('/characters/batch-capacity')
).data

export const buildCharacter = async (payload: {
  name: string
  description: string
  source_object_key: string
  prompt_profile?: CharacterPromptProfile
}) => (await api.post('/characters/build', payload)).data

export const createCharacterDraft = async (payload: {
  name: string
  description: string
  source_object_key: string
  prompt_profile?: CharacterPromptProfile
}): Promise<CharacterReference> => (
  await api.post('/characters/drafts', payload)
).data

export const generateCharacterView = async (
  id: string,
  viewType: CharacterViewType,
  prompt: string,
  engine: CharacterViewEngine,
) => (
  await api.post(`/characters/${id}/views/${viewType}/generate`, { prompt, engine })
).data

export const uploadCharacterView = async (
  id: string,
  viewType: CharacterViewType,
  sourceObjectKey: string,
): Promise<CharacterReferenceView> => (
  await api.post(`/characters/${id}/views/${viewType}/upload`, {
    source_object_key: sourceObjectKey,
  })
).data

export const saveCharacterReference = async (
  id: string,
): Promise<CharacterReference> => (
  await api.post(`/characters/${id}/save`)
).data

export const updateCharacter = async (id: string, payload: { name?: string; description?: string }) => (
  await api.patch(`/characters/${id}`, payload)
).data

export const deleteCharacter = async (id: string) => api.delete(`/characters/${id}`)
