import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import QqccConfigApp from './QqccConfigApp.vue'
import { installAntDesign } from './plugins/antDesign'

const app = createApp(QqccConfigApp)
installAntDesign(app)
app.mount('#app')
