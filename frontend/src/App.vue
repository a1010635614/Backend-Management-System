<script setup lang="ts">
import { BookOpen, PenLine, Search, UserRound } from 'lucide-vue-next'
import AnalyticsConsent from './components/AnalyticsConsent.vue'
</script>
<template><AnalyticsConsent/><div class="shell"><header class="topbar"><RouterLink class="brand" to="/"><span class="brand-icon"><BookOpen :size="19"/></span><span>纸间.</span></RouterLink><nav><RouterLink to="/">首页</RouterLink><RouterLink to="/admin">管理后台</RouterLink></nav><div class="actions"><RouterLink class="write-btn" to="/write"><PenLine :size="15"/> 写文章</RouterLink><RouterLink class="avatar" to="/login" title="邮箱登录"><UserRound :size="17"/></RouterLink></div></header><main><RouterView /></main><footer><span>© 2026 纸间博客</span><span>把日子写成值得回看的句子。</span></footer></div></template>
