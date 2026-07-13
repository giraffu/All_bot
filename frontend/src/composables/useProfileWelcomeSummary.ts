import { computed, type ComputedRef } from 'vue'
import dayjs from 'dayjs'

type ProfileUser = {
  current_identity?: string | null
  identity_expire_at?: string | null
  user_group?: string | null
}

type Translate = (key: string) => string

export function useProfileWelcomeSummary(options: {
  user: ComputedRef<ProfileUser | null | undefined>
  t: Translate
}) {
  const formatDate = (dateString?: string | null) => {
    if (!dateString) return options.t('profile.valid_forever')
    return dayjs(dateString).format('YYYY-MM-DD HH:mm')
  }

  const identityExpireText = computed(() => {
    if (
      options.user.value?.current_identity === '外门弟子' ||
      !options.user.value?.identity_expire_at
    ) {
      return options.t('profile.valid_forever')
    }
    return `${options.t('profile.valid_until')}${formatDate(options.user.value?.identity_expire_at)}`
  })

  const userGroupLabel = computed(() =>
    options.user.value?.user_group
      ? options.t(`group.${options.user.value.user_group}`)
      : options.t('group.凡人')
  )

  const identityLabel = computed(() =>
    options.user.value?.current_identity
      ? options.t(`identity.${options.user.value.current_identity}`)
      : options.t('identity.外门弟子')
  )

  return {
    identityExpireText,
    userGroupLabel,
    identityLabel,
  }
}
