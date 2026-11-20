<script setup lang="ts">
import {ElMessage} from 'element-plus'
import {useRouter} from 'vue-router'
import {useAuthStore} from '../stores/auth'
import {errorMessage} from '../lib/http'
const auth=useAuthStore(),router=useRouter()
const webUrl=import.meta.env.VITE_WEB_URL||(import.meta.env.DEV?'http://127.0.0.1:5173/':'/')
async function logout(){try{await auth.logout();await router.replace('/login')}catch(e){ElMessage.error(errorMessage(e))}}
</script>
<template><el-result icon="warning" title="暂无后台访问权限" sub-title="当前账号是读者。请联系管理员分配编辑或管理员角色。"><template #extra><a :href="webUrl"><el-button>返回博客</el-button></a><el-button type="primary" @click="logout">切换账号</el-button></template></el-result></template>
