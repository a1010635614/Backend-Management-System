<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowUpRight, Clock3, Eye, Search, Sparkles } from '@lucide/vue'
import { useArticleStore } from '../stores/articles'
const store = useArticleStore(), route = useRoute(), router = useRouter()
const query = ref(String(route.query.q || ''))
const page = computed(() => Math.max(1, Number(route.query.page) || 1))
const category = computed(() => String(route.query.category || ''))
const pages = computed(() => Math.max(1, Math.ceil(store.total / 9)))
watch(() => route.query, () => { query.value = String(route.query.q || ''); void store.load(page.value, query.value, category.value) }, { immediate: true })
onMounted(() => void store.loadCategories())
function filter(next: Record<string, string | number>) { void router.push({ path: '/', query: { ...route.query, page: 1, ...next } }) }
function date(value: string) { return new Date(value).toLocaleDateString('zh-CN') }
</script>
<template>
  <section class="hero"><div class="hero-copy"><span class="eyebrow"><Sparkles :size="14"/> 一处安放心事的角落</span><h1>写给日常，<br/><em>也写给远方。</em></h1><p>收藏生活的细碎片段，<br/>记录那些值得慢慢讲述的故事。</p><a class="hero-link" href="#articles">开始阅读 <ArrowDown :size="16"/></a></div><div class="paper-art" aria-hidden="true"><div class="paper-back"></div><div class="paper-front"><span class="paper-label">THE QUIET JOURNAL</span><div class="sun"></div><div class="mountains"><i></i><i></i><i></i></div><p>在寻常的日子里，<br/>看见一些不寻常。</p><span class="paper-number">NOTES / 01</span></div><span class="art-star">✳</span></div><div class="hero-bottom"><span>SCROLL TO EXPLORE</span><span class="line"></span><span>A PLACE FOR WORDS</span></div></section>
  <section id="articles" class="articles"><div class="section-head"><div><span class="eyebrow">THE JOURNAL</span><h2>最近的文章 <small>{{store.total.toString().padStart(2, '0')}}</small></h2></div><form class="search-form" @submit.prevent="filter({q:query})"><label class="sr-only" for="search">搜索文章</label><input id="search" v-model="query" placeholder="找一篇文章…" maxlength="100"/><button aria-label="搜索"><Search :size="18"/></button></form></div>
  <div class="categories"><button :class="{selected:!category}" @click="filter({category:''})">全部</button><button v-for="item in store.categories" :key="item.name" :class="{selected:category===item.name}" @click="filter({category:item.name})">{{item.name}} <span>{{item.count}}</span></button></div>
  <div v-if="store.loading" class="empty" role="status">正在翻开新的一页…</div><div v-else-if="store.error" class="empty" role="alert"><p>{{store.error}}</p><button class="button" @click="store.load(page,query,category)">重新加载</button></div><div v-else-if="!store.posts.length" class="empty"><h3>这一页，等故事开始。</h3><p>{{query||category?'换一个关键词或分类试试。':'暂时还没有公开文章，欢迎过些时候再来。'}}</p></div>
  <div v-else class="post-grid"><article v-for="(post,index) in store.posts" :key="post.id" class="post-card"><RouterLink :to="`/posts/${post.id}`" class="post-art" :class="`pattern-${index%3}`" :aria-label="post.title"><span>{{post.category}}</span><b>{{String((page-1)*9+index+1).padStart(2,'0')}}</b><ArrowUpRight :size="22"/></RouterLink><div class="post-meta"><span>{{post.category}}</span><time :datetime="post.createdAt">{{date(post.createdAt)}}</time></div><h3><RouterLink :to="`/posts/${post.id}`">{{post.title}}</RouterLink></h3><p>{{post.summary}}</p><div class="post-foot"><span><Clock3 :size="14"/> {{post.readMinutes}} 分钟阅读</span><span><Eye :size="14"/> {{post.views}}</span></div></article></div>
  <nav v-if="pages>1" class="pagination" aria-label="文章分页"><button class="button ghost" :disabled="page<=1" @click="filter({page:page-1})">上一页</button><span>{{page}} / {{pages}}</span><button class="button ghost" :disabled="page>=pages" @click="filter({page:page+1})">下一页</button></nav></section>
  <section id="about" class="note"><span class="eyebrow">A SMALL NOTE</span><p>把日子写成<br/>值得回看的句子。</p><span>这里是纸间，很高兴遇见你。</span></section>
</template>
