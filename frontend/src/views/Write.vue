<script setup lang="ts">
import { ref,onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
const route=useRoute()
onMounted(async()=>{if(route.query.id){try{const p=await api(`/posts/${route.query.id}`);title.value=p.title;content.value=p.content}catch(e){message.value=String(e)}}})
const title=ref(''),content=ref(''),message=ref('')
async function upload(event:Event){const file=(event.target as HTMLInputElement).files?.[0];if(!file)return;if(file.size>10*1024*1024){message.value='文件不能超过 10MB';return}try{const signed=await api(`/uploads/presign?filename=${encodeURIComponent(file.name)}&content_type=${encodeURIComponent(file.type)}`,{method:'POST'});const response=await fetch(signed.uploadUrl,{method:'PUT',headers:{'Content-Type':file.type},body:file});if(!response.ok)throw Error('上传失败');content.value+=`\n${signed.publicUrl}`;message.value='上传完成'}catch(e){message.value=String(e)}}
async function publish(){message.value='';try{await api(route.query.id?`/posts/${route.query.id}`:'/posts',{method:route.query.id?'PUT':'POST',body:JSON.stringify({title:title.value,summary:content.value.slice(0,120),content:content.value,category:'生活随笔'})});message.value='文章已保存'}catch(e){message.value=String(e)}}
</script>
<template><section class="editor"><span class="eyebrow">NEW STORY</span><h1>写下此刻</h1><input v-model="title" placeholder="给这篇文章一个标题"/><textarea v-model="content" placeholder="从一个念头开始……"></textarea><label>上传图片或 PDF<input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" @change="upload"/></label><div class="editor-actions"><span role="status">{{message}}</span><button class="write-btn" @click="publish">保存文章</button><RouterLink to="/admin">返回后台</RouterLink></div></section></template>
