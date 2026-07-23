import { describe, expect, it } from 'vitest'
import { i18n } from './i18n'

describe('bilingual catalog', () => {
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
})
