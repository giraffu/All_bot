import 'ant-design-vue/dist/reset.css'
import '../../../shared/web/theme-tokens.css'
import './style.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import i18n from './i18n'
import router from './router'

createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
