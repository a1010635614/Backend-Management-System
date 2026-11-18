<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router=useRouter(),email=ref(''),code=ref(''),message=ref(''),busy=ref(false)
let captcha:any=null,captchaId=''
declare global { interface Window { initGeetest4?: (config:object,cb:(captcha:any)=>void)=>void } }
onMounted(async()=>{try{captchaId=(await api('/auth/config')).captchaId;if(captchaId){const script=document.createElement('script');script.src='https://static.geetest.com/v4/gt4.js';script.onload=()=>window.initGeetest4?.({captchaId,product:'bind'},c=>{captcha=c;c.onSuccess(()=>send(c.getValidate()))});script.onerror=()=>message.value='验证服务加载失败，请刷新';document.head.appendChild(script)}}catch(e){message.value=String(e)}})
async function send(geetest:object={}){busy.value=true;try{await api('/auth/email/send',{method:'POST',body:JSON.stringify({email:email.value,geetest})});message.value='验证码已发送，五分钟内有效'}catch(e){message.value=String(e)}finally{busy.value=false}}
function requestCode(){if(captchaId){if(captcha)captcha.showCaptcha();else message.value='验证服务正在加载'}else void send()}
async function login(){busy.value=true;try{const data=await api('/auth/email/verify',{method:'POST',body:JSON.stringify({email:email.value,code:code.value})});sessionStorage.setItem('token',data.access_token);await router.push('/admin')}catch(e){message.value=String(e)}finally{busy.value=false}}
</script>
<template><section class="editor"><span class="eyebrow">WELCOME BACK</span><h1>邮箱登录</h1><form @submit.prevent="login"><input v-model="email" type="email" required placeholder="你的邮箱地址" autocomplete="email"/><button class="write-btn" type="button" :disabled="busy||!email" @click="requestCode">发送验证码</button><input v-model="code" required pattern="[0-9]{6}" placeholder="六位验证码" autocomplete="one-time-code"/><p role="status">{{message}}</p><button class="write-btn" :disabled="busy">登录</button></form></section></template>
