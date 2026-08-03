import { effectScope, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/api', () => ({ default: { get, post } }))
vi.mock('ant-design-vue', () => ({
  message: { error: vi.fn(), info: vi.fn() },
}))

import { usePromptOptimizer } from './usePromptOptimizer'

describe('usePromptOptimizer', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    const values = new Map<string, string>()
    vi.stubGlobal('sessionStorage', {
      clear: () => values.clear(),
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    })
    vi.stubGlobal('window', { setTimeout })
    vi.stubGlobal('crypto', { randomUUID: () => 'request-uuid' })
  })

  it('loads capabilities, submits selected version and supports undo', async () => {
    get
      .mockResolvedValueOnce({
        data: {
          templates: [
            {
              id: 'ltx_scene_script_cinematic',
              version: 3,
              label: '成人电影化提示词',
              description: '默认增强成人 NSFW 动作、镜头与多人连续性',
              is_default: true,
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: { status: 'success', result_text: 'optimized prompt' },
      })
    post.mockResolvedValueOnce({ data: { task_id: 'task-1' } })

    const scope = effectScope()
    const mode = ref<'ltx_video_v2'>('ltx_video_v2')
    const prompt = ref('original prompt')
    const duration = ref('5')
    const references = ref([{ key: 'web_uploads/7/start.png', preview: '', name: 'start' }])
    const optimizer = scope.run(() => usePromptOptimizer({
      currentModeId: mode,
      prompt,
      duration,
      uploadedReferences: references,
    }))!

    await nextTick()
    await Promise.resolve()
    await optimizer.optimizePrompt()

    expect(post.mock.calls[0][1]).toMatchObject({
      client_request_id: 'request-uuid',
      template: { id: 'ltx_scene_script_cinematic', version: 3 },
      context: { duration_seconds: 5 },
      media: [{ role: 'start_image', object_key: 'web_uploads/7/start.png' }],
    })
    expect(prompt.value).toBe('optimized prompt')
    optimizer.restoreOriginalPrompt()
    expect(prompt.value).toBe('original prompt')
    scope.stop()
  })
})
