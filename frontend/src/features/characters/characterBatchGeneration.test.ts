import { describe, expect, it, vi } from 'vitest'

import {
  getMissingCharacterViewTypes,
  runCharacterViewBatch,
} from './characterBatchGeneration'

describe('character view batch generation', () => {
  it('selects only views that are not ready or pending', () => {
    expect(getMissingCharacterViewTypes(
      ['face_front', 'face_side', 'body_front'],
      [
        { type: 'face_front', status: 'ready' },
        { type: 'face_side', status: 'pending' },
      ],
    )).toEqual(['body_front'])
  })

  it('fills the live concurrency capacity and continues after a slot is released', async () => {
    const submit = vi.fn().mockResolvedValue(undefined)
    const getCapacity = vi.fn()
      .mockResolvedValueOnce({ limit: 3, active: 1, available: 2 })
      .mockResolvedValueOnce({ limit: 3, active: 2, available: 1 })
    const waitForCapacity = vi.fn().mockResolvedValue(undefined)
    const progress: Array<{ submitted: number; remaining: number }> = []

    const result = await runCharacterViewBatch({
      viewTypes: ['face_front', 'face_side', 'body_front'],
      getCapacity,
      submit,
      waitForCapacity,
      isActive: () => true,
      onProgress: value => progress.push(value),
    })

    expect(submit.mock.calls.map(call => call[0])).toEqual([
      'face_front',
      'face_side',
      'body_front',
    ])
    expect(waitForCapacity).toHaveBeenCalledOnce()
    expect(progress.at(-1)).toEqual({ submitted: 3, remaining: 0 })
    expect(result).toEqual({ submitted: 3, failed: 0, cancelled: false })
  })
})
