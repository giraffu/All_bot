import api from '@/api'

export type OfficialReferenceAsset = {
  id: string
  source: 'official'
  name: string
  description: string
  preview_url?: string | null
  category?: string | null
}

export const fetchOfficialCharacters = async (): Promise<OfficialReferenceAsset[]> =>
  (await api.get('/reference-assets/characters')).data

export const fetchOfficialEnvironments = async (): Promise<OfficialReferenceAsset[]> =>
  (await api.get('/reference-assets/environments')).data
