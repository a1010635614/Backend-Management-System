<script setup lang="ts">
import {ref,onMounted} from 'vue'
import {useRoute} from 'vue-router'
import {api} from '../api'
const route=useRoute(),post=ref<{title:string,content:string,category:string,createdAt:string}|null>(null),error=ref('')
onMounted(async()=>{try{post.value=await api(`/posts/${route.params.id}`)}catch(e){error.value=String(e)}})
</script>
<template><article class="editor"><RouterLink to="/">← 返回文章列表</RouterLink><p v-if="error" role="alert">{{error}}</p><template v-else-if="post"><p class="eyebrow">{{post.category}} · {{new Date(post.createdAt).toLocaleDateString('zh-CN')}}</p><h1>{{post.title}}</h1><div class="article-content">{{post.content}}</div></template><p v-else>正在加载文章…</p></article></template>
<style scoped>.article-content{white-space:pre-wrap;overflow-wrap:anywhere;line-height:2.1;font-size:16px;margin-top:32px}</style>
