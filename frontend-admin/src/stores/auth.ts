import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Router } from 'vue-router'
import { http } from '../lib/http'
import type { AdminRoute, AuthResult, User } from '../lib/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem('blog-token') || '')
  const user = ref<User | null>(null), routes = ref<AdminRoute[]>([]), ready = ref(false)
  let pending: Promise<void> | null = null
  let activeRouter: Router | null = null
  const can = computed(() => (permission: string) => user.value?.permissions.includes(permission) || false)
  function bindRouter(router: Router) { activeRouter = router }
  function reset() {
    for(const route of routes.value) activeRouter?.removeRoute(route.name)
    token.value=''; user.value=null; routes.value=[]; ready.value=false; pending=null
    sessionStorage.removeItem('blog-token')
  }
  async function bootstrap() {
    if(ready.value) return
    if(pending) return pending
    pending = (async () => {
      const response = await http.get<User>('/auth/me')
      user.value = response.data
      routes.value = (await http.get<AdminRoute[]>('/admin/routes')).data
      ready.value = true
    })()
    try { await pending } finally { pending=null }
  }
  async function login(email:string, code:string) {
    reset()
    const {data} = await http.post<AuthResult>('/auth/email/verify',{email,code})
    token.value=data.access_token; sessionStorage.setItem('blog-token',data.access_token)
    user.value=data.user
  }
  async function logout() { await http.post('/auth/logout'); reset() }
  return {token,user,routes,ready,can,bindRouter,reset,bootstrap,login,logout}
})
