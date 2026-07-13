import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import App from './App.vue'
import { installAntDesign } from './plugins/antDesign'

const app = createApp(App)
installAntDesign(app)
app.mount('#app')
