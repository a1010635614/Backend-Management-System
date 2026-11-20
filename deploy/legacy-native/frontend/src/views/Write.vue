<script setup lang="ts">
import { ref,onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
const route=useRoute()
onMounted(async()=>{if(route.query.id){try{const p=await api(`/posts/${route.query.id}`);title.value=p.title;content.value=p.content;category.value=p.category}catch(e){message.value=String(e)}}})
const title=ref(''),content=ref(''),category=ref('生活随笔'),message=ref(''),busy=ref(false)
async function upload(event:Event){
  const input=event.target as HTMLInputElement,file=input.files?.[0]
  if(!file)return
  if(!file.size||file.size>10*1024*1024){message.value='请选择 10MB 以内的非空文件';return}
  busy.value=true;message.value='正在上传…'
  try{
    const signed=await api('/uploads/presign',{method:'POST',body:JSON.stringify({filename:file.name,contentType:file.type,size:file.size})})
    const response=await fetch(signed.uploadUrl,{method:'PUT',headers:{'Content-Type':file.type},body:file})
    if(!response.ok)throw Error('上传失败，请重试')
    const asset=await api(`/uploads/${signed.id}/complete`,{method:'POST'})
    content.value+=`\n[[asset:${asset.id}]]\n`;message.value='附件已上传并确认，保存文章后读者可访问'
  }catch(e){message.value=String(e)}finally{busy.value=false;input.value=''}
}
async function publish(){
  busy.value=true;message.value=''
  try{
    const summary=content.value.replace(/\[\[asset:[a-f0-9-]{36}\]\]/g,'').trim().slice(0,120)||title.value
    await api(route.query.id?`/posts/${route.query.id}`:'/posts',{method:route.query.id?'PUT':'POST',body:JSON.stringify({title:title.value,summary,content:content.value,category:category.value})})
    message.value='文章已保存'
  }catch(e){message.value=String(e)}finally{busy.value=false}
}
</script>
<template><section class="editor"><span class="eyebrow">NEW STORY</span><h1>写下此刻</h1><form @submit.prevent="publish"><input v-model="title" required maxlength="180" placeholder="给这篇文章一个标题"/><input v-model="category" required maxlength="60" placeholder="文章分类"/><textarea v-model="content" required placeholder="从一个念头开始……"></textarea><label>上传图片或 PDF<input type="file" :disabled="busy" accept="image/jpeg,image/png,image/webp,application/pdf" @change="upload"/></label><div class="editor-actions"><span role="status">{{message}}</span><button class="write-btn" :disabled="busy">保存文章</button><RouterLink to="/admin">返回后台</RouterLink></div></form></section></template>
