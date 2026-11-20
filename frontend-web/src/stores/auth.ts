import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { http } from '../lib/http'
import type { AuthResult, User } from '../lib/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem('blog-token') || '')
  const user = ref<User | null>(null)
  const authenticated = computed(() => !!token.value && !!user.value)
  function reset() { token.value = ''; user.value = null; sessionStorage.removeItem('blog-token') }
  async function refresh() {
    if (!token.value) return
    try { user.value = (await http.get<User>('/auth/me')).data } catch { reset() }
  }
  async function login(email: string, code: string) {
    const { data } = await http.post<AuthResult>('/auth/email/verify', { email, code })
    token.value = data.access_token; user.value = data.user
    sessionStorage.setItem('blog-token', data.access_token)
  }
  async function logout() { await http.post('/auth/logout'); reset() }
  return { token, user, authenticated, reset, refresh, login, logout }
})
