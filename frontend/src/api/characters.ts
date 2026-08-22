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
  adult_confirmed: boolean
  usage_rights_confirmed: boolean
  default_prompts: Partial<Record<CharacterViewType, string>>
  view_configs?: CharacterViewConfig[]
  views: CharacterReferenceView[]
}

export type CharacterViewConfig = {
  type: CharacterViewType
  label: string
  required: boolean
  can_generate: boolean
  has_templates: boolean
  custom: boolean
  tag_groups: CharacterTagGroup[]
  tag_options: Record<CharacterTagGroup, Record<string, string>>
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
  description: string | null
  prompt: string
  default_prompt: string
  tag_groups?: CharacterTagGroup[]
  tag_options?: Record<CharacterTagGroup, Record<string, string>>
  status: 'pending' | 'ready' | 'failed'
  task_id: string | null
  object_key: string | null
  preview_url: string | null
}

export type CharacterTagGroup = 'breast_size' | 'pubic_hair' | 'skin_tone'

export type CharacterViewType =
  | 'face_front'
  | 'body_front_nude'
  | 'body_front_clothed'
  | 'torso_front'
  | 'genitals_front'
  | 'pelvis_back'
  | 'custom_1'
  | 'custom_2'
  | 'custom_3'
  | 'custom_4'

export type CharacterViewImageTemplate = {
  id: string
  view_type: 'torso_front' | 'genitals_front' | 'pelvis_back'
  name: string
  gender: 'neutral' | 'female' | 'male'
  sort_order: number
  is_default: boolean
  preview_url: string
}

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
  prompt_profile: CharacterPromptProfile
  adult_confirmed: true
  usage_rights_confirmed: true
}) => (await api.post('/characters/build', payload)).data

export const createCharacterDraft = async (payload: {
  name: string
  description?: string
  source_object_key?: string
  template_id?: string
  initial_view_type: CharacterViewType
  initial_view_label?: string
  prompt_profile?: CharacterPromptProfile
}): Promise<CharacterReference> => (
  await api.post('/characters/drafts', payload)
).data

export const confirmCharacterReference = async (id: string, payload: {
  prompt_profile?: CharacterPromptProfile
  adult_confirmed: true
  usage_rights_confirmed: true
}): Promise<CharacterReference> => (
  await api.post(`/characters/${id}/confirm`, payload)
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

export const fetchCharacterViewTemplates = async (): Promise<CharacterViewImageTemplate[]> => (
  await api.get('/characters/view-templates')
).data

export const applyCharacterViewTemplate = async (
  id: string,
  viewType: CharacterViewType,
  templateId: string,
): Promise<CharacterReferenceView> => (
  await api.post(`/characters/${id}/views/${viewType}/template`, {
    template_id: templateId,
  })
).data

export const updateCharacterView = async (
  id: string,
  viewType: CharacterViewType,
  payload: { display_name?: string; description?: string },
): Promise<CharacterReferenceView> => (
  await api.patch(`/characters/${id}/views/${viewType}`, payload)
).data

export const saveCharacterReference = async (
  id: string,
): Promise<CharacterReference> => (
  await api.post(`/characters/${id}/save`)
).data

export const updateCharacter = async (id: string, payload: { name?: string; description?: string; prompt_profile?: CharacterPromptProfile }) => (
  await api.patch(`/characters/${id}`, payload)
).data

export const deleteCharacter = async (id: string) => api.delete(`/characters/${id}`)
