import api from '@/api'

interface LocaleRef {
  value: string
}

export function useProfileLanguage(locale: LocaleRef) {
  const toggleLanguage = async () => {
    const newLang = locale.value === 'zh' ? 'en' : 'zh'
    locale.value = newLang

    try {
      await api.patch('/users/preferences', { language_code: newLang })
    } catch (error) {
      console.error('Failed to save language preference', error)
    }
  }

  return {
    toggleLanguage
  }
}
