<script setup lang="ts">
import { ref } from 'vue'
import { enableAnalytics } from '../lib/analytics'
const visible = ref(!localStorage.getItem('analytics-consent'))
function choose(agree: boolean) {
  localStorage.setItem('analytics-consent', agree ? 'yes' : 'no'); visible.value = false
  if (agree) void enableAnalytics()
}
</script>
<template><aside v-if="visible" class="consent" aria-label="访问统计选择"><p>允许匿名访问统计，帮助了解文章的阅读情况。可继续浏览而不参与统计。</p><div><button class="button ghost" @click="choose(false)">暂不参与</button><button class="button" @click="choose(true)">同意</button></div></aside></template>
