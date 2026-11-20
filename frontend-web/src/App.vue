<script setup lang="ts">
import { BookOpen, PenLine, UserRound } from '@lucide/vue'
import { ref } from 'vue'
import { useAuthStore } from './stores/auth'
import { errorMessage } from './lib/http'
import AnalyticsConsent from './components/AnalyticsConsent.vue'
const auth = useAuthStore(), error = ref('')
const adminUrl = import.meta.env.VITE_ADMIN_URL || (import.meta.env.DEV ? 'http://127.0.0.1:5174/admin/' : '/admin/')
async function logout() { try { await auth.logout() } catch (e) { error.value = errorMessage(e) } }
</script>
<template><a class="skip-link" href="#main">跳到正文</a><div class="shell"><header class="topbar"><RouterLink class="brand" to="/" aria-label="纸间首页"><span class="brand-icon"><BookOpen :size="19"/></span><span>纸间.</span></RouterLink><nav aria-label="主导航"><RouterLink to="/">首页</RouterLink><a href="/#about">关于纸间</a></nav><div class="actions"><a class="button write-link" :href="adminUrl"><PenLine :size="15"/> 管理后台</a><button v-if="auth.authenticated" class="avatar" :title="`${auth.user?.email}，点击退出`" aria-label="退出登录" @click="logout"><UserRound :size="18"/></button><RouterLink v-else class="avatar" to="/login" aria-label="邮箱登录"><UserRound :size="18"/></RouterLink></div></header><p v-if="error" class="error" role="alert">{{error}}</p><main id="main"><RouterView/></main><footer class="site-footer"><span>© {{new Date().getFullYear()}} 纸间博客</span><span>把日子写成值得回看的句子。</span></footer></div><AnalyticsConsent/></template>
