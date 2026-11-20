<script setup lang="ts">
import {ref} from 'vue'
import {enableAnalytics} from '../analytics'
const show=ref(!localStorage.getItem('analytics-consent'))
function choose(yes:boolean){localStorage.setItem('analytics-consent',yes?'yes':'no');show.value=false;if(yes)void enableAnalytics()}
</script>
<template><aside v-if="show" class="consent" aria-label="访问统计选择"><p>是否允许匿名访问统计？同意后将向本站及百度统计发送页面路径和随机访客标识，用于统计 PV/UV。</p><button class="write-btn" @click="choose(true)">同意</button> <button @click="choose(false)">暂不同意</button></aside></template>
<style scoped>.consent{position:fixed;bottom:20px;left:20px;max-width:420px;padding:20px;background:#fff;box-shadow:0 5px 35px #0002;z-index:20;font-size:13px;line-height:1.8}</style>
