import { createI18n } from 'vue-i18n'

import zh from '../../shared/locales/zh.json'
import en from '../../shared/locales/en.json'

const i18n = createI18n({
  legacy: false, // use Composition API
  locale: 'zh',  // default locale
  fallbackLocale: 'zh',
  messages: {
    zh,
    en
  }
})

export default i18n
