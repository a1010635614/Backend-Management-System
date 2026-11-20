import { defineStore } from 'pinia'
import { ref } from 'vue'
import { http, errorMessage } from '../lib/http'
import type { Page, Post } from '../lib/types'

export const useArticleStore = defineStore('articles', () => {
  const posts = ref<Post[]>([]), total = ref(0), loading = ref(false), error = ref('')
  const categories = ref<{name: string; count: number}[]>([])
  let revision = 0
  async function load(page = 1, q = '', category = '') {
    const request = ++revision
    loading.value = true; error.value = ''
    try {
      const { data } = await http.get<Page<Post>>('/posts', { params: { page, page_size: 9, q, category } })
      if (request === revision) { posts.value = data.items; total.value = data.total }
    } catch (e) { if (request === revision) error.value = errorMessage(e) }
    finally { if (request === revision) loading.value = false }
  }
  async function loadCategories() {
    try { categories.value = (await http.get<{name: string; count: number}[]>('/categories')).data } catch { /* Article list remains available. */ }
  }
  return { posts, total, loading, error, categories, load, loadCategories }
})
