<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Clock3, Eye } from '@lucide/vue'
import { http, errorMessage } from '../lib/http'
import { renderMarkdown } from '../lib/markdown'
import type { Post } from '../lib/types'
const route = useRoute(), post = ref<Post | null>(null), error = ref(''), loading = ref(true)
const html = computed(() => renderMarkdown(post.value?.content || '', post.value?.attachments))
watch(() => route.params.id, async (id, _, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort())
  loading.value = true; post.value = null; error.value = ''
  try {
    const { data } = await http.get<Post>(`/posts/${id}`, { signal: controller.signal })
    if (!controller.signal.aborted) { post.value = data; document.title = `${data.title} · 纸间`; void http.post(`/posts/${id}/view`).catch(() => {}) }
  } catch (e) { if (!controller.signal.aborted) error.value = errorMessage(e) }
  finally { if (!controller.signal.aborted) loading.value = false }
}, { immediate: true })
</script>
<template><article class="reading"><RouterLink to="/" class="back-link"><ArrowLeft :size="16"/> 返回文章列表</RouterLink><div v-if="loading" class="empty" role="status">正在加载文章…</div><div v-else-if="error" class="empty" role="alert"><h1>暂时无法翻开这一页</h1><p>{{error}}</p></div><template v-else-if="post"><header class="reading-head"><span class="eyebrow">{{post.category}} · {{new Date(post.createdAt).toLocaleDateString('zh-CN')}}</span><h1>{{post.title}}</h1><p>{{post.summary}}</p><div class="post-foot"><span><Clock3 :size="15"/> {{post.readMinutes}} 分钟阅读</span><span><Eye :size="15"/> {{post.views}}</span></div></header><div class="markdown-body" v-html="html"></div><footer class="reading-end">— 感谢读到这里 —</footer></template></article></template>
