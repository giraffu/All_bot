import { describe, expect, it } from 'vitest'
import { resolveTaskTypeLabel } from '@/utils/taskTypePresentation'

const labels: Record<string, string> = {
  'task_type.txt2img': 'Text2Img',
  'task_type.pornmaster_flux2_edit_bf16': 'Free Edit v3',
  'task_type.other': 'Generation Task',
}

const t = (key: string) => labels[key] ?? key
const te = (key: string) => key in labels

describe('resolveTaskTypeLabel', () => {
  it('localizes known internal task types', () => {
    expect(resolveTaskTypeLabel('pornmaster-flux2-edit-bf16', t, te)).toBe(
      'Free Edit v3',
    )
  })

  it('never exposes an unknown internal type', () => {
    expect(resolveTaskTypeLabel('secret_worker_model', t, te)).toBe(
      'Generation Task',
    )
  })
})
