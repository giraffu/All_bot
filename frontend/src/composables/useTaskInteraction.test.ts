// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'

import { resolveTaskDownloadUrl } from './useTaskInteraction'

describe('resolveTaskDownloadUrl', () => {
  it('prefers backend-provided output_file_url', () => {
    const getFileUrl = vi.fn(() => 'https://storage.example.com/fallback.png')

    const result = resolveTaskDownloadUrl(
      {
        output_file: 'bot-data/history/task-1/output.png',
        output_file_url: 'https://signed.example.com/output.png'
      },
      getFileUrl
    )

    expect(result).toBe('https://signed.example.com/output.png')
    expect(getFileUrl).not.toHaveBeenCalled()
  })

  it('falls back to storage path when output_file_url is absent', () => {
    const getFileUrl = vi.fn(() => 'https://storage.example.com/output.png')

    const result = resolveTaskDownloadUrl(
      {
        output_file: 'bot-data/history/task-1/output.png'
      },
      getFileUrl
    )

    expect(result).toBe('https://storage.example.com/output.png')
    expect(getFileUrl).toHaveBeenCalledWith('bot-data/history/task-1/output.png')
  })
})
