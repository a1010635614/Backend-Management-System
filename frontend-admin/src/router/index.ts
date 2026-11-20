import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const components: Record<string, NonNullable<RouteRecordRaw['component']>> = {
  Dashboard: () => import('../views/Dashboard.vue'), Articles: () => import('../views/Articles.vue'),
  Editor: () => import('../views/Editor.vue'), Users: () => import('../views/Users.vue'),
}
export const router = createRouter({ history:createWebHistory(import.meta.env.BASE_URL), routes:[
  {path:'/login',name:'login',component:()=>import('../views/Login.vue'),meta:{public:true,title:'管理员登录'}},
  {path:'/403',name:'forbidden',component:()=>import('../views/Forbidden.vue'),meta:{title:'无访问权限'}},
  {path:'/',name:'shell',component:()=>import('../layouts/AdminLayout.vue'),children:[]},
  {path:'/:pathMatch(.*)*',name:'not-found',component:()=>import('../views/NotFound.vue'),meta:{title:'页面未找到'}},
],scrollBehavior:()=>({top:0})})

router.beforeEach(async to=>{
  const auth=useAuthStore(); auth.bindRouter(router)
  if(to.meta.public) return true
  if(!auth.token) return {name:'login',query:{redirect:to.fullPath}}
  try {
    await auth.bootstrap()
    let added=false
    for(const item of auth.routes) {
      if(!router.hasRoute(item.name) && components[item.component]) {
        router.addRoute('shell',{path:item.path,name:item.name,component:components[item.component],
          meta:{title:item.title,permission:item.permission,hidden:item.hidden}})
        added=true
      }
    }
    if(to.path==='/') return auth.routes.length ? auth.routes[0]!.path : '/403'
    if(added && to.name==='not-found') return {path:to.path,query:to.query,hash:to.hash,replace:true}
    if(to.meta.permission && !auth.can(String(to.meta.permission))) return '/403'
    if(!auth.routes.length && to.name!=='forbidden') return '/403'
    document.title=`${String(to.meta.title||'管理后台')} · 纸间`
    return true
  } catch { auth.reset(); return {name:'login',query:{redirect:to.fullPath}} }
})
