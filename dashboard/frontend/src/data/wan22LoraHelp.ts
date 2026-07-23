import rawCatalog from './wan22LoraHelp.zh-CN.json'

export interface Wan22LoraStrengthStage {
  min: number
  max: number
  recommended: number
}

export interface Wan22LoraPromptExample {
  prompt: string
  translation_zh: string
}

export interface Wan22LoraHelpModel {
  category: string
  purpose: string
  trigger_words: string[]
  strength: {
    high: Wan22LoraStrengthStage
    low: Wan22LoraStrengthStage
    source: string
  }
  model_page: string
  prompt_examples: Wan22LoraPromptExample[]
  notes: string[]
}

interface Wan22LoraHelpCatalog {
  schema_version: number
  source_bundle: string
  source_readme: string
  models: Record<string, Wan22LoraHelpModel>
}

export const wan22LoraHelpCatalog = rawCatalog as Wan22LoraHelpCatalog

export function getWan22LoraHelp(modelKey: string): Wan22LoraHelpModel | undefined {
  return wan22LoraHelpCatalog.models[modelKey]
}
