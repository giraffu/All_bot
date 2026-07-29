import { createI18n } from 'vue-i18n'

import sharedEn from '../../../shared/locales/en.json'
import sharedZh from '../../../shared/locales/zh.json'
import en from './locales/en'
import zh from './locales/zh'

export default createI18n({
  legacy: false,
  locale: localStorage.getItem('avatar_miniapp_locale') === 'en' ? 'en' : 'zh',
  fallbackLocale: 'zh',
  messages: {
    zh: { ...sharedZh, miniapp: zh },
    en: { ...sharedEn, miniapp: en },
  },
})
