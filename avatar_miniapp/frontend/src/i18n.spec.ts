import { describe, expect, it } from 'vitest'

import i18n from './i18n'

describe('avatar mini app translations', () => {
  it('provides the core studio flow in both languages', () => {
    i18n.global.locale.value = 'zh'
    expect(i18n.global.t('miniapp.build.disclaimer')).toContain('不会根据上传照片')

    i18n.global.locale.value = 'en'
    expect(i18n.global.t('miniapp.render.submit')).toContain('CPU')
  })
})
