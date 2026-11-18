<script setup lang="ts">
import {ref,onMounted,computed} from 'vue'
import {useRoute} from 'vue-router'
import {api} from '../api'
type Attachment={id:string,filename:string,contentType:string,url:string}
type Part={text:string,asset?:Attachment}
const route=useRoute(),post=ref<{title:string,content:string,category:string,createdAt:string,attachments?:Attachment[]}|null>(null),error=ref('')
const parts=computed<Part[]>(()=>{
  if(!post.value)return []
  const text=post.value.content,assets=new Map((post.value.attachments||[]).map(a=>[a.id,a])),result:Part[]=[]
  let offset=0
  for(const match of text.matchAll(/\[\[asset:([a-f0-9-]{36})\]\]/g)){
    if(match.index!>offset)result.push({text:text.slice(offset,match.index)})
    const asset=assets.get(match[1]);result.push(asset?{text:'',asset}:{text:'附件暂不可用'})
    offset=match.index!+match[0].length
  }
  if(offset<text.length)result.push({text:text.slice(offset)})
  return result
})
onMounted(async()=>{try{post.value=await api(`/posts/${route.params.id}`)}catch(e){error.value=String(e)}})
</script>
<template><article class="editor"><RouterLink to="/">← 返回文章列表</RouterLink><p v-if="error" role="alert">{{error}}</p><template v-else-if="post"><p class="eyebrow">{{post.category}} · {{new Date(post.createdAt).toLocaleDateString('zh-CN')}}</p><h1>{{post.title}}</h1><div class="article-content"><template v-for="(part,index) in parts" :key="index"><span v-if="part.asset" class="attachment"><img v-if="part.asset.contentType.startsWith('image/')" :src="part.asset.url" :alt="part.asset.filename" loading="lazy"/><a :href="part.asset.url" target="_blank" rel="noopener noreferrer">{{part.asset.filename}}</a></span><span v-else>{{part.text}}</span></template></div></template><p v-else>正在加载文章…</p></article></template>
<style scoped>.article-content{white-space:pre-wrap;overflow-wrap:anywhere;line-height:2.1;font-size:16px;margin-top:32px}.attachment{display:block;margin:20px 0}.attachment img{display:block;max-width:100%;height:auto}.attachment a{font-size:14px;color:#415640}</style>
