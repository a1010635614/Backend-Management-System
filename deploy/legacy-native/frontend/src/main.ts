import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import {track,enableAnalytics} from './analytics'
const router = createRouter({ history: createWebHistory(), routes: [{ path: '/', component: () => import('./views/Home.vue') }, { path: '/write', component: () => import('./views/Write.vue') }, {path:'/login',component:()=>import('./views/Login.vue')},{path:'/admin',component:()=>import('./views/Admin.vue')}] })
router.beforeEach(to=>{if(['/write','/admin'].includes(to.path)&&!sessionStorage.getItem('token'))return '/login'})
router.addRoute({path:'/posts/:id',component:()=>import('./views/Detail.vue')})
createApp(App).use(router).mount('#app')
router.afterEach(to=>track(to.path))
void router.isReady().then(()=>{if(localStorage.getItem('analytics-consent')==='yes')void enableAnalytics()})
