import { message } from 'ant-design-vue'
import { copyTextWithFallback } from '@/utils/clipboard'

interface PromptCarrier {
  prompt?: string | null
}

export function usePostPromptCopy(
  t: (key: string) => string
) {
  const copyPrompt = (post: PromptCarrier) => {
    const prompt = post.prompt?.trim()
    if (!prompt) {
      message.warning(t('my_notes.prompt_empty'))
      return
    }

    void copyTextWithFallback(prompt).then((successful) => {
      if (successful) {
        message.success(t('my_notes.prompt_copied'))
      } else {
        message.error(t('my_notes.copy_failed'))
      }
    })
  }

  return {
    copyPrompt
  }
}
