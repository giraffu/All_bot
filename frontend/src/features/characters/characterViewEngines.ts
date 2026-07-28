import type { CharacterViewEngine } from '@/api/characters'

export type CharacterViewEngineOption = {
  value: CharacterViewEngine
  labelKey: string
  cost: number
}

export const CHARACTER_VIEW_ENGINE_OPTIONS: CharacterViewEngineOption[] = [
  { value: 'free_edit', labelKey: 'characters.engines.free_edit', cost: 2 },
  { value: 'free_edit_v2_5', labelKey: 'characters.engines.free_edit_v2_5', cost: 3 },
  { value: 'free_edit_v3', labelKey: 'characters.engines.free_edit_v3', cost: 5 },
]

export const getCharacterViewEngineCost = (engine: CharacterViewEngine): number => (
  CHARACTER_VIEW_ENGINE_OPTIONS.find(option => option.value === engine)?.cost ?? 3
)
