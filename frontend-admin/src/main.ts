import {createApp} from 'vue'
import {createPinia} from 'pinia'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import App from './App.vue'
import {router} from './router'
import {useAuthStore} from './stores/auth'
import './style.css'

const app=createApp(App), pinia=createPinia()
app.use(pinia).use(router)
window.addEventListener('blog:unauthorized',()=>{
  useAuthStore(pinia).reset()
  if(router.currentRoute.value.name!=='login') void router.replace('/login')
})
app.mount('#app')
