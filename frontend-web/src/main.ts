import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { enableAnalytics, track } from './lib/analytics'
import { useAuthStore } from './stores/auth'
import './style.css'

const router = createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes: [
  {path:'/',component:()=>import('./views/Home.vue'),meta:{title:'日常与远方'}},
  {path:'/posts/:id',component:()=>import('./views/Detail.vue'),meta:{title:'阅读文章'}},
  {path:'/login',component:()=>import('./views/Login.vue'),meta:{title:'邮箱登录'}},
  {path:'/:pathMatch(.*)*',component:()=>import('./views/NotFound.vue'),meta:{title:'页面未找到'}},
], scrollBehavior(to,from,saved) { return saved || (to.hash ? {el:to.hash,behavior:'smooth'} : {top:0}) } })
const app = createApp(App), pinia = createPinia()
app.use(pinia).use(router)
const auth = useAuthStore(pinia)
window.addEventListener('blog:unauthorized', () => auth.reset())
router.afterEach((to, _from, failure) => {
  if (failure) return
  document.title = `${String(to.meta.title || '日常与远方')} · 纸间`
  track(to.path)
})
app.mount('#app')
void auth.refresh()
void router.isReady().then(() => { if(localStorage.getItem('analytics-consent')==='yes') void enableAnalytics() })
