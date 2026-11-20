<script setup lang="ts">
import {computed,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {ElMessage} from 'element-plus'
import {Document,House,User,Reading,SwitchButton,Menu as MenuIcon} from '@element-plus/icons-vue'
import {useAuthStore} from '../stores/auth'
import {errorMessage} from '../lib/http'
const auth=useAuthStore(), route=useRoute(), router=useRouter(), mobile=ref(false)
const menu=computed(()=>auth.routes.filter(item=>!item.hidden))
const icons:Record<string,unknown>={dashboard:House,articles:Document,users:User}
const webUrl=import.meta.env.VITE_WEB_URL||(import.meta.env.DEV?'http://127.0.0.1:5173/':'/')
async function logout(){try{await auth.logout();await router.replace('/login')}catch(e){ElMessage.error(errorMessage(e))}}
</script>
<template><div class="admin-shell"><aside class="sidebar" :class="{open:mobile}"><a class="admin-brand" :href="webUrl"><el-icon :size="25"><Reading/></el-icon><span>纸间<span class="brand-dot">.</span><small>工作台</small></span></a><span class="menu-caption">内容与运营</span><el-menu :default-active="String(route.name)" class="sidebar-menu"><el-menu-item v-for="item in menu" :key="item.name" :index="item.name" @click="router.push(item.path);mobile=false"><el-icon><component :is="icons[item.name]||Document"/></el-icon><span>{{item.title}}</span></el-menu-item></el-menu><div class="sidebar-bottom"><p>让每一个故事，<br/>都有值得停留的地方。</p><a :href="webUrl" target="_blank" rel="noopener noreferrer">打开博客 ↗</a></div></aside><div class="admin-workspace"><header class="admin-topbar"><div class="breadcrumb"><button class="mobile-menu" aria-label="展开菜单" @click="mobile=!mobile"><el-icon><MenuIcon/></el-icon></button><span>工作台</span><span>/</span><b>{{route.meta.title}}</b></div><div class="admin-account"><span class="role-badge">{{auth.user?.role==='admin'?'管理员':'编辑'}}</span><span class="account-email">{{auth.user?.email}}</span><el-button text :icon="SwitchButton" @click="logout">退出</el-button></div></header><main class="admin-content"><RouterView/></main><footer class="admin-footer">纸间内容管理 · {{new Date().getFullYear()}}</footer></div></div></template>
