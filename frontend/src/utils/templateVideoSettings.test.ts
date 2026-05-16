import { describe, expect, it } from 'vitest'
import {
  canLockTemplateVideoPromptControls,
  getTemplateVideoSettings,
  normalizePersistedTierBillingResolution,
  resolveTierBillingResolution,
  toPositiveInteger
} from './templateVideoSettings'

describe('templateVideoSettings', () => {
  it('rejects nullish and non-positive values', () => {
    expect(toPositiveInteger(null)).toBeNull()
    expect(toPositiveInteger(undefined)).toBeNull()
    expect(toPositiveInteger('')).toBeNull()
    expect(toPositiveInteger('   ')).toBeNull()
    expect(toPositiveInteger(0)).toBeNull()
    expect(toPositiveInteger('0')).toBeNull()
    expect(toPositiveInteger(-1)).toBeNull()
    expect(toPositiveInteger('abc')).toBeNull()
  })

  it('rejects incomplete template values', () => {
    expect(getTemplateVideoSettings({ width: null, duration: null })).toBeNull()
    expect(getTemplateVideoSettings({ width: 1024, duration: null })).toBeNull()
    expect(getTemplateVideoSettings({ width: 1280, height: null, duration: 10 }, true)).toBeNull()
  })

  it('normalizes valid template values', () => {
    expect(getTemplateVideoSettings({ width: '1024', duration: '8' })).toEqual({
      width: 1024,
      height: null,
      duration: 8
    })
    expect(getTemplateVideoSettings({ width: '1280', height: '704', duration: '10' }, true)).toEqual({
      width: 1280,
      height: 704,
      duration: 10
    })
  })

  it('locks prompt controls only when template prompt config is complete', () => {
    expect(
      canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'custom_video')
    ).toBe(true)
    expect(
      canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'ltx_video')
    ).toBe(true)
    expect(
      canLockTemplateVideoPromptControls({ prompt: 'cinematic motion blur' }, 'video_lora')
    ).toBe(false)
    expect(
      canLockTemplateVideoPromptControls(
        { prompt: 'cinematic motion blur', lora_name: 'BreastGrow' },
        'video_lora'
      )
    ).toBe(true)
    expect(
      canLockTemplateVideoPromptControls({ prompt: '   ', lora_name: 'BreastGrow' }, 'video_lora')
    ).toBe(false)
  })

  it('normalizes persisted billing tiers and explicit resolutions', () => {
    expect(normalizePersistedTierBillingResolution('720p')).toBe('720')
    expect(normalizePersistedTierBillingResolution('1024')).toBe('1024')
    expect(normalizePersistedTierBillingResolution('640x800')).toBe('720')
    expect(normalizePersistedTierBillingResolution('bad-tier')).toBeNull()
  })

  it('prefers persisted billing tiers and falls back to width-height inference', () => {
    expect(
      resolveTierBillingResolution({
        billing_resolution: '720p',
        width: 640,
        height: 800
      })
    ).toBe('720')

    expect(
      resolveTierBillingResolution({
        billing_resolution: null,
        width: 1024,
        height: 576
      })
    ).toBe('1024')
  })
})
