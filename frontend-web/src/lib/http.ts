import axios from 'axios'

export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 15000 })
http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('blog-token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
http.interceptors.response.use(response => response, error => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    sessionStorage.removeItem('blog-token')
    window.dispatchEvent(new Event('blog:unauthorized'))
  }
  return Promise.reject(error)
})
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    return error.response ? `请求失败（${error.response.status}）` : '网络连接失败，请稍后重试'
  }
  return error instanceof Error ? error.message : '操作失败，请重试'
}
