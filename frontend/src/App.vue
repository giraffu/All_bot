<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import enUS from 'ant-design-vue/es/locale/en_US'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'

const { locale } = useI18n()

const antLocale = computed(() => {
  return locale.value === 'en' ? enUS : zhCN
})

watch(locale, (val) => {
  dayjs.locale(val === 'en' ? 'en' : 'zh-cn')
}, { immediate: true })

</script>

<template>
  <a-config-provider :locale="antLocale">
    <router-view />
  </a-config-provider>
</template>
