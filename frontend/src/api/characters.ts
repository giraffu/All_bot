import api from './index'

export type CharacterReference = {
  id: string
  name: string
  description: string | null
  status: 'pending' | 'ready' | 'failed'
  task_id: string
  source_object_key: string
  sheet_object_key: string | null
  preview_url: string | null
}

export const fetchCharacters = async (): Promise<CharacterReference[]> => (
  await api.get('/characters')
).data

export const buildCharacter = async (payload: {
  name: string
  description?: string
  source_object_key: string
}) => (await api.post('/characters/build', payload)).data

export const updateCharacter = async (id: string, payload: { name?: string; description?: string }) => (
  await api.patch(`/characters/${id}`, payload)
).data

export const deleteCharacter = async (id: string) => api.delete(`/characters/${id}`)
