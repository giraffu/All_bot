import { describe, expect, it } from 'vitest'

import { getRateLimitFallbackKey } from './errorMessages'

describe('getRateLimitFallbackKey', () => {
  it('uses the queue-capacity guidance only for task submission', () => {
    expect(getRateLimitFallbackKey('/tasks/generate')).toBe('api.generation_queue_full')
    expect(getRateLimitFallbackKey('/gallery/posts/1/comments')).toBe('api.too_many_tasks')
  })
})
