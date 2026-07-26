const generationTaskEndpoint = /(^|\/)tasks\/generate(?:\?|$)/

export function getRateLimitFallbackKey(url?: string): string {
  return generationTaskEndpoint.test(url ?? '')
    ? 'api.generation_queue_full'
    : 'api.too_many_tasks'
}
