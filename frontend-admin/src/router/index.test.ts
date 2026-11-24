import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import type {Router} from 'vue-router'
import type {AdminRoute, User} from '../lib/types'

const menus: AdminRoute[] = [
  {name:'dashboard',path:'/dashboard',component:'Dashboard',title:'概览',permission:'analytics:read'},
  {name:'articles',path:'/articles',component:'Articles',title:'文章',permission:'posts:read'},
  {name:'article-edit',path:'/articles/:id/edit',component:'Editor',title:'编辑',permission:'posts:write',hidden:true},
  {name:'users',path:'/users',component:'Users',title:'用户',permission:'users:manage'},
]
let router: Router
let auth: ReturnType<(typeof import('../stores/auth'))['useAuthStore']>
let profile: User
let expired = false
let requests: {method:string;url:string;authorization:unknown}[]

beforeEach(async()=>{
  vi.resetModules()
  // Vitest uses its own base URL; emulate the production /admin/ mount explicitly.
  vi.stubEnv('BASE_URL','/admin/')
  vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
  sessionStorage.clear()
  window.history.replaceState({},'', '/admin/')
  const {createPinia,setActivePinia}=await import('pinia')
  setActivePinia(createPinia())
  profile={id:1,email:'admin@example.com',role:'admin',permissions:['analytics:read','posts:read','posts:write','users:manage']}
  expired=false
  requests=[]
  const {AxiosError}=await import('axios')
  const {http}=await import('../lib/http')
  // Replace only the network boundary; run the real Axios interceptors, store and router.
  http.defaults.adapter=async config=>{
    requests.push({method:config.method||'get',url:config.url||'',authorization:config.headers.Authorization})
    const response={config,status:200,statusText:'OK',headers:{},data:undefined as unknown}
    if(expired && config.url==='/auth/me') {
      throw new AxiosError('Expired session','ERR_BAD_REQUEST',config,undefined,
        {...response,status:401,statusText:'Unauthorized',data:{detail:'登录已失效'}})
    }
    if(config.url==='/auth/me') response.data=profile
    else if(config.url==='/admin/routes') response.data=menus.filter(item=>profile.permissions.includes(item.permission))
    else if(config.url==='/auth/logout') response.status=204
    else if(config.url==='/auth/email/verify') response.data={access_token:'editor-fixture-token',token_type:'bearer',expires_in:3600,user:profile}
    else throw new Error(`Unexpected request in isolated router check: ${config.url}`)
    return response
  }
  router=(await import('./index')).router
  auth=(await import('../stores/auth')).useAuthStore()
})

afterEach(()=>{
  router?.options.history.destroy()
  sessionStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

function session() {
  sessionStorage.setItem('blog-token','admin-fixture-token')
  auth.token='admin-fixture-token'
}

describe('后台动态路由与真实认证状态协作',{timeout:15_000},()=>{
  it('匿名深链接跳转登录并保留站内目标，不请求管理接口',async()=>{
    await router.push('/articles/42/edit')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/articles/42/edit')
    expect(router.hasRoute('article-edit')).toBe(false)
    expect(requests).toEqual([])
  })

  it('管理员首次打开 History 深链接时加载菜单并重新匹配编辑路由',async()=>{
    session()
    await router.push('/articles/42/edit')
    expect(router.currentRoute.value.name).toBe('article-edit')
    expect(router.currentRoute.value.params.id).toBe('42')
    expect(window.location.pathname).toBe('/admin/articles/42/edit')
    expect(router.hasRoute('users')).toBe(true)
    expect(requests.map(item=>item.url)).toEqual(['/auth/me','/admin/routes'])
    expect(requests.every(item=>item.authorization==='Bearer admin-fixture-token')).toBe(true)
    expect(auth.can('users:manage')).toBe(true)
  })

  it('编辑可进入文章管理，但不会注册管理员用户路由',async()=>{
    profile={id:2,email:'editor@example.com',role:'editor',permissions:['posts:read','posts:write']}
    session()
    await router.push('/articles')
    expect(router.currentRoute.value.name).toBe('articles')
    await router.push('/users')
    expect(router.currentRoute.value.name).toBe('not-found')
    expect(router.hasRoute('users')).toBe(false)
    expect(auth.can('users:manage')).toBe(false)
    expect(requests.map(item=>item.url)).toEqual(['/auth/me','/admin/routes'])
  })

  it('普通用户菜单为空时进入无权限页面，不循环重定向或加载管理路由',async()=>{
    profile={id:3,email:'viewer@example.com',role:'viewer',permissions:[]}
    session()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('forbidden')
    expect(auth.routes).toEqual([])
    expect(router.hasRoute('dashboard')).toBe(false)
    expect(router.hasRoute('article-edit')).toBe(false)
    expect(requests).toHaveLength(2)
  })

  it('退出清除动态路由及令牌，换成编辑登录后不会继承管理员菜单',async()=>{
    session()
    await router.push('/users')
    expect(router.hasRoute('users')).toBe(true)
    await auth.logout()
    expect(router.hasRoute('users')).toBe(false)
    expect(sessionStorage.getItem('blog-token')).toBeNull()
    expect(auth.user).toBeNull()
    profile={id:2,email:'editor@example.com',role:'editor',permissions:['posts:read','posts:write']}
    await auth.login(profile.email,'123456')
    await router.push('/users?changed=editor')
    expect(router.currentRoute.value.name).toBe('not-found')
    expect(router.hasRoute('users')).toBe(false)
    expect(auth.user?.role).toBe('editor')
    expect(sessionStorage.getItem('blog-token')).toBe('editor-fixture-token')
  })

  it('会话初始化收到401时触发失效事件并回登录页，不保留权限状态',async()=>{
    session()
    expired=true
    const dispatch=vi.spyOn(window,'dispatchEvent')
    await router.push('/dashboard')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/dashboard')
    expect(sessionStorage.getItem('blog-token')).toBeNull()
    expect(auth.token).toBe('')
    expect(auth.user).toBeNull()
    expect(auth.routes).toEqual([])
    expect(router.hasRoute('dashboard')).toBe(false)
    expect(dispatch.mock.calls.some(([event])=>event.type==='blog:unauthorized')).toBe(true)
    expect(requests.map(item=>item.url)).toEqual(['/auth/me'])
  })
})
