import { describe, expect, it } from 'vitest'

import {
  CHARACTER_VIEW_ENGINE_OPTIONS,
  getCharacterViewEngineCost,
} from './characterViewEngines'

describe('character view engines', () => {
  it('offers the three standard free-edit flows with their existing prices', () => {
    expect(CHARACTER_VIEW_ENGINE_OPTIONS.map(option => [
      option.value,
      option.cost,
    ])).toEqual([
      ['free_edit', 2],
      ['free_edit_v2_5', 3],
      ['free_edit_v3', 5],
    ])
    expect(getCharacterViewEngineCost('free_edit_v3')).toBe(5)
  })
})
