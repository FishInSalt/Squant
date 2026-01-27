import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
// @ts-ignore - Element Plus locale module
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import pinia from './stores'
import './styles/global.scss'

const app = createApp(App)

// 注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
app.use(ElementPlus, { locale: zhCn as any })
app.use(router)
app.use(pinia)

app.mount('#app')
