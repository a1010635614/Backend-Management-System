<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Mail } from '@lucide/vue'
import { http, errorMessage } from '../lib/http'
import { challenge } from '../lib/geetest'
import { useAuthStore } from '../stores/auth'
const auth = useAuthStore(), router = useRouter(), email = ref(''), code = ref(''), busy = ref(false), message = ref(''), error = ref(''), countdown = ref(0)
let timer: ReturnType<typeof setInterval> | undefined
onUnmounted(() => clearInterval(timer))
async function send() {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) { error.value = '请填写有效的邮箱地址'; return }
  busy.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await http.get<{captchaId:string;captchaRequired:boolean}>('/auth/config')
    const proof = await challenge(data.captchaId, data.captchaRequired)
    const result = await http.post<{expiresIn:number}>('/auth/email/send', { email: email.value.trim(), geetest: proof })
    countdown.value = result.data.expiresIn; message.value = '验证码已发送，请查收邮箱。'
    clearInterval(timer); timer = setInterval(() => { if (countdown.value>0) countdown.value--; else clearInterval(timer) }, 1000)
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function login() {
  busy.value = true; error.value = ''
  try { await auth.login(email.value.trim(), code.value); await router.push('/') } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
</script>
<template><section class="login-page"><div class="login-intro"><span class="eyebrow">WELCOME BACK</span><h1>让故事，<br/>从一封邮件开始。</h1><p>无需记住密码。完成行为验证后，<br/>用邮箱验证码安全登录。</p></div><form class="login-card" @submit.prevent="login"><div class="login-icon"><Mail :size="25"/></div><h2>邮箱登录</h2><p class="muted">请输入你能正常收信的邮箱</p><label for="email">邮箱地址</label><input id="email" v-model="email" type="email" autocomplete="email" required maxlength="320" placeholder="you@example.com" :disabled="busy"/><label for="code">六位验证码</label><div class="code-row"><input id="code" v-model="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="000000" required/><button class="button ghost" type="button" :disabled="busy||countdown>0" @click="send">{{countdown?`${countdown} 秒后重发`:'发送验证码'}}</button></div><p v-if="message" class="success" role="status">{{message}}</p><p v-if="error" class="error" role="alert">{{error}}</p><button class="button login-submit" :disabled="busy">{{busy?'正在处理…':'登录纸间'}}</button><RouterLink to="/" class="muted">← 返回首页</RouterLink></form></section></template>
