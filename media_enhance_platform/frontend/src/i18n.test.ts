import { describe, expect, it } from 'vitest'
import { i18n } from './i18n'

describe('bilingual catalog', () => {
  it('starts in Chinese and exposes the Chinese product brand', () => {
    expect(i18n.global.locale.value).toBe('zh')
    expect(i18n.global.t('brand.name')).toBe('真境智影')
  })

  it('switches the same product message between Chinese and English', () => {
    i18n.global.locale.value = 'zh'
    expect(i18n.global.t('home.imageTitle')).toBe('图片高清')
    i18n.global.locale.value = 'en'
    expect(i18n.global.t('home.imageTitle')).toBe('Image clarity')
    i18n.global.locale.value = 'zh'
  })

  it('contains status copy for the no-worker V1 state', () => {
    expect(i18n.global.t('workspace.noWorker')).toBe('等待算力接入')
  })

  it('publishes the approved ICP filing number', () => {
    i18n.global.locale.value = 'zh'
    expect(i18n.global.t('legal.icp')).toBe('鄂ICP备2026044153号-1')
  })
})
