import { describe, expect, it } from 'vitest'
import {
  canLockTemplateVideoPromptControls,
  getTemplateVideoSettings,
  inferLegacyTierVideoRequestedDuration,
  inferLegacyLtxRequestedDuration,
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

  it('prefers requested_duration over probed duration when available', () => {
    expect(
      getTemplateVideoSettings({
        width: '1280',
        height: '704',
        duration: '1',
        requested_duration: '20'
      }, true, 'ltx_video')
    ).toEqual({
      width: 1280,
      height: 704,
      duration: 20
    })
  })

  it('maps nearby legacy ltx media durations back to canonical request tiers', () => {
    expect(inferLegacyLtxRequestedDuration(6)).toBe(5)
    expect(inferLegacyLtxRequestedDuration(7)).toBe(5)
    expect(inferLegacyLtxRequestedDuration(8)).toBe(10)
    expect(inferLegacyLtxRequestedDuration(9)).toBe(10)
    expect(inferLegacyLtxRequestedDuration('11')).toBe(10)
    expect(inferLegacyLtxRequestedDuration(13)).toBe(15)
    expect(inferLegacyLtxRequestedDuration(16)).toBe(15)
    expect(inferLegacyLtxRequestedDuration(17)).toBe(15)
    expect(inferLegacyLtxRequestedDuration(18)).toBe(20)
    expect(inferLegacyLtxRequestedDuration(19)).toBe(20)
    expect(inferLegacyLtxRequestedDuration('21')).toBe(20)
    expect(inferLegacyLtxRequestedDuration(22)).toBe(20)
    expect(inferLegacyLtxRequestedDuration(1)).toBeNull()
    expect(inferLegacyLtxRequestedDuration(23)).toBeNull()
  })

  it('maps nearby legacy tier-video media durations back to canonical request tiers', () => {
    expect(inferLegacyTierVideoRequestedDuration(5)).toBe(5)
    expect(inferLegacyTierVideoRequestedDuration(6)).toBe(5)
    expect(inferLegacyTierVideoRequestedDuration(7)).toBe(8)
    expect(inferLegacyTierVideoRequestedDuration(8)).toBe(8)
    expect(inferLegacyTierVideoRequestedDuration(9)).toBe(8)
    expect(inferLegacyTierVideoRequestedDuration(10)).toBe(10)
    expect(inferLegacyTierVideoRequestedDuration(11)).toBe(10)
    expect(inferLegacyTierVideoRequestedDuration(12)).toBe(10)
    expect(inferLegacyTierVideoRequestedDuration(1)).toBeNull()
    expect(inferLegacyTierVideoRequestedDuration(13)).toBeNull()
  })

  it('uses nearest legacy ltx duration compatibility when canonical duration is missing', () => {
    expect(
      getTemplateVideoSettings({
        width: '512',
        height: '704',
        duration: '16',
        requested_duration: null
      }, true, 'ltx_video')
    ).toEqual({
      width: 512,
      height: 704,
      duration: 15
    })
  })

  it('falls back to 5s when tier-video requested_duration is missing', () => {
    expect(
      getTemplateVideoSettings({
        width: '720',
        height: '1280',
        duration: '9',
        requested_duration: null
      }, false, 'custom_video')
    ).toEqual({
      width: 720,
      height: 1280,
      duration: 5
    })
  })

  it('restores canonical requested_duration for tier-video templates', () => {
    expect(
      getTemplateVideoSettings({
        width: '720',
        height: '1280',
        duration: '9',
        requested_duration: 8
      }, false, 'custom_video')
    ).toEqual({
      width: 720,
      height: 1280,
      duration: 8
    })
  })

  it('rejects dirty probed duration for legacy ltx_video templates without canonical duration', () => {
    expect(
      getTemplateVideoSettings({
        width: '1344',
        height: '768',
        duration: '1',
        requested_duration: null
      }, true, 'ltx_video')
    ).toBeNull()
  })

  it('ignores dirty probed duration for legacy tier-video templates', () => {
    expect(
      getTemplateVideoSettings({
        width: '720',
        height: '1280',
        duration: '13',
        requested_duration: null
      }, false, 'custom_video')
    ).toEqual({
      width: 720,
      height: 1280,
      duration: 5
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
    expect(normalizePersistedTierBillingResolution('720p')).toBe('standard')
    expect(normalizePersistedTierBillingResolution('small')).toBe('small')
    expect(normalizePersistedTierBillingResolution('0.26 MP - Preview')).toBe('preview')
    expect(normalizePersistedTierBillingResolution('0.36 MP - Small')).toBe('small')
    expect(normalizePersistedTierBillingResolution('0.52 MP - SD')).toBe('standard')
    expect(normalizePersistedTierBillingResolution('0.65 MP - Balanced')).toBe('hd')
    expect(normalizePersistedTierBillingResolution('1024')).toBe('hd')
    expect(normalizePersistedTierBillingResolution('720x1280')).toBe('standard')
    expect(normalizePersistedTierBillingResolution('600x960')).toBe('small')
    expect(normalizePersistedTierBillingResolution('512x768')).toBe('preview')
    expect(normalizePersistedTierBillingResolution('1024x1536')).toBe('hd')
    expect(normalizePersistedTierBillingResolution('bad-tier')).toBeNull()
  })

  it('prefers persisted billing tiers and falls back to width-height inference', () => {
    expect(
      resolveTierBillingResolution({
        billing_resolution: '720p',
        width: 640,
        height: 800
      })
    ).toBe('standard')

    expect(
      resolveTierBillingResolution({
        billing_resolution: null,
        width: 720,
        height: 1280
      })
    ).toBe('standard')

    expect(
      resolveTierBillingResolution({
        billing_resolution: null,
        width: 600,
        height: 960
      })
    ).toBe('small')

    expect(
      resolveTierBillingResolution({
        billing_resolution: null,
        width: 512,
        height: 768
      })
    ).toBe('preview')

    expect(
      resolveTierBillingResolution({
        billing_resolution: null,
        width: 1024,
        height: 1536
      })
    ).toBe('hd')
  })
})
