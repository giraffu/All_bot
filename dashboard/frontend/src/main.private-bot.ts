import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import PrivateBotOwnerApp from './PrivateBotOwnerApp.vue'
import { installAntDesign } from './plugins/antDesign'

const app = createApp(PrivateBotOwnerApp)
installAntDesign(app)
app.mount('#app')
