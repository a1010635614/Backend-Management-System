<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router=useRouter(),posts=ref<any[]>([]),stats=ref({pv:0,uv:0}),message=ref(''),email=ref(''),pending=ref<number|null>(null)
onMounted(async()=>{try{email.value=(await api('/auth/me')).email;[posts.value,stats.value]=await Promise.all([api('/posts'),api('/analytics/summary')])}catch(e){message.value=String(e)}})
async function remove(id:number){try{await api(`/posts/${id}`,{method:'DELETE'});posts.value=posts.value.filter(p=>p.id!==id);pending.value=null}catch(e){message.value=String(e)}}
function logout(){sessionStorage.removeItem('token');router.push('/login')}
</script>
<template><section class="editor"><span class="eyebrow">DASHBOARD</span><h1>管理后台</h1><p>{{email}} <button @click="logout">退出登录</button></p><p role="alert">{{message}}</p><div class="stats"><div>今日 PV<strong>{{stats.pv}}</strong></div><div>今日 UV<strong>{{stats.uv}}</strong></div><div>文章<strong>{{posts.length}}</strong></div></div><RouterLink class="write-btn" to="/write">新建文章</RouterLink><table><thead><tr><th>文章标题</th><th>分类</th><th>操作</th></tr></thead><tbody><tr v-for="post in posts" :key="post.id"><td>{{post.title}}</td><td>{{post.category}}</td><td><RouterLink :to="`/write?id=${post.id}`">编辑</RouterLink> <button v-if="pending!==post.id" @click="pending=post.id">删除</button><template v-else><button @click="remove(post.id)">确认删除</button><button @click="pending=null">取消</button></template></td></tr></tbody></table></section></template>
