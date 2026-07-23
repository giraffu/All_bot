// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'

import {
  hasFrontendUpdate,
  startFrontendUpdateMonitor,
} from './releaseUpdateMonitor'

describe('release update monitor', () => {
  it('detects when the no-store dashboard entry points at a newer main asset', () => {
    const html = `
      <!doctype html>
      <script type="module" crossorigin src="/assets/main-new123.js"></script>
    `

    expect(
      hasFrontendUpdate(
        'https://dashboard.example/assets/main-old456.js',
        html,
        'https://dashboard.example',
      ),
    ).toBe(true)
    expect(
      hasFrontendUpdate(
        'https://dashboard.example/assets/main-new123.js',
        html,
        'https://dashboard.example',
      ),
    ).toBe(false)
  })

  it('reloads an open dashboard after a newly deployed entry asset is observed', async () => {
    const fetchHtml = vi.fn().mockResolvedValue(`
      <script type="module" src="/assets/main-new123.js"></script>
    `)
    const reload = vi.fn()

    const monitor = startFrontendUpdateMonitor({
      currentEntryUrl: 'https://dashboard.example/assets/main-old456.js',
      origin: 'https://dashboard.example',
      fetchHtml,
      reload,
      intervalMs: 60_000,
    })
    await monitor.check()
    monitor.stop()

    expect(fetchHtml).toHaveBeenCalledOnce()
    expect(reload).toHaveBeenCalledOnce()
  })
})
