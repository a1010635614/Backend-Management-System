<script setup lang="ts">
import {onUnmounted,reactive,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import type {FormInstance,FormRules} from 'element-plus'
import {Reading,Message} from '@element-plus/icons-vue'
import {http,errorMessage} from '../lib/http'
import {challenge} from '../lib/geetest'
import {useAuthStore} from '../stores/auth'
const router=useRouter(),route=useRoute(),auth=useAuthStore(),formRef=ref<FormInstance>()
const form=reactive({email:'',code:''}),busy=ref(false),countdown=ref(0),error=ref(''),message=ref('')
const rules:FormRules={email:[{required:true,message:'请输入邮箱',trigger:'blur'},{type:'email',message:'邮箱格式不正确',trigger:'blur'}],code:[{required:true,message:'请输入验证码',trigger:'blur'},{pattern:/^\d{6}$/,message:'请输入六位数字验证码',trigger:'blur'}]}
let timer:ReturnType<typeof setInterval>|undefined
onUnmounted(()=>clearInterval(timer))
async function send(){
  if(!await formRef.value?.validateField('email').then(()=>true).catch(()=>false))return
  busy.value=true;error.value='';message.value=''
  try{
    const {data}=await http.get<{captchaId:string;captchaRequired:boolean}>('/auth/config')
    const geetest=await challenge(data.captchaId,data.captchaRequired)
    const response=await http.post<{expiresIn:number}>('/auth/email/send',{email:form.email.trim(),geetest})
    countdown.value=response.data.expiresIn;message.value='验证码已发送，请查收邮箱。'
    clearInterval(timer);timer=setInterval(()=>{if(countdown.value>0)countdown.value--;else clearInterval(timer)},1000)
  }catch(e){error.value=errorMessage(e)}finally{busy.value=false}
}
async function login(){
  if(!await formRef.value?.validate().catch(()=>false))return
  busy.value=true;error.value=''
  try{await auth.login(form.email.trim(),form.code);const next=String(route.query.redirect||'/');await router.replace(next.startsWith('/')&&!next.startsWith('//')?next:'/')}
  catch(e){error.value=errorMessage(e)}finally{busy.value=false}
}
</script>
<template><main class="admin-login"><div class="login-story"><div class="login-brand"><el-icon :size="30"><Reading/></el-icon> 纸间.</div><p class="section-kicker">A PLACE FOR YOUR WORDS</p><h1>管理好灵感，<br/>然后，写下生活。</h1><p>属于你的内容工作台。<br/>让每一次记录，都井然有序。</p><span class="login-story-bottom">THE QUIET JOURNAL / WORKSPACE</span></div><div class="login-form-wrap"><div class="login-form-card"><el-icon class="login-mail-icon" :size="28"><Message/></el-icon><h2>欢迎回到纸间</h2><p>完成行为验证，使用邮箱验证码登录。</p><el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="login"><el-form-item label="邮箱地址" prop="email"><el-input v-model="form.email" size="large" type="email" autocomplete="email" placeholder="you@example.com" :disabled="busy"/></el-form-item><el-form-item label="六位验证码" prop="code"><div class="admin-code-row"><el-input v-model="form.code" size="large" maxlength="6" inputmode="numeric" autocomplete="one-time-code" placeholder="000000"/><el-button size="large" :disabled="busy||countdown>0" @click="send">{{countdown?`${countdown} 秒后重发`:'发送验证码'}}</el-button></div></el-form-item><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/><el-alert v-if="message" :title="message" type="success" :closable="false" show-icon/><el-button class="admin-login-submit" type="primary" size="large" native-type="submit" :loading="busy">登录工作台</el-button></el-form><p class="login-security-note">菜单和操作权限由服务端角色授权。</p></div></div></main></template>
