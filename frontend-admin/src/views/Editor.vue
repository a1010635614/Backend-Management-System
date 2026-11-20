<script setup lang="ts">
import {computed,onBeforeUnmount,reactive,ref,watch} from 'vue'
import {onBeforeRouteLeave,useRoute,useRouter} from 'vue-router'
import axios from 'axios'
import {ElMessage,ElMessageBox} from 'element-plus'
import type {FormInstance,FormRules} from 'element-plus'
import {Upload,Check,Document,Refresh} from '@element-plus/icons-vue'
import {http,errorMessage} from '../lib/http'
import {renderMarkdown} from '../lib/markdown'
import type {Attachment,Post} from '../lib/types'

const route=useRoute(),router=useRouter(),formRef=ref<FormInstance>(),fileInput=ref<HTMLInputElement>()
const form=reactive({title:'',summary:'',category:'生活随笔',content:'',status:'draft' as 'draft'|'published'})
const assets=ref<Attachment[]>([]),previews=ref<Record<string,string>>({}),baseline=ref('')
const loading=ref(false),saving=ref(false),uploading=ref(false),progress=ref(0),error=ref(''),previewError=ref('')
const html=computed(()=>renderMarkdown(form.content,assets.value,previews.value))
const dirty=computed(()=>!!baseline.value&&JSON.stringify(form)!==baseline.value)
const rules:FormRules={title:[{required:true,message:'请填写文章标题',trigger:'blur'}],summary:[{required:true,message:'请填写文章摘要',trigger:'blur'}],category:[{required:true,message:'请填写分类',trigger:'blur'}],content:[{required:true,message:'请写一点内容',trigger:'blur'}]}

async function refreshPreviews(){
  previewError.value=''
  for(let offset=0;offset<assets.value.length;offset+=4){
    await Promise.all(assets.value.slice(offset,offset+4).map(async asset=>{
      try{const {data}=await http.get<{url:string}>(`/uploads/${asset.id}/preview`);previews.value[asset.id]=data.url}
      catch{previewError.value='部分附件预览暂不可用，可稍后刷新。'}
    }))
  }
}
watch(()=>route.params.id,async(id,_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  loading.value=true;error.value='';assets.value=[];previews.value={}
  Object.assign(form,{title:'',summary:'',category:'生活随笔',content:'',status:'draft'})
  baseline.value=JSON.stringify(form)
  try{
    if(id){const {data}=await http.get<Post>(`/admin/posts/${id}`,{signal:abort.signal});if(abort.signal.aborted)return;Object.assign(form,{title:data.title,summary:data.summary,category:data.category,content:data.content||'',status:data.status});assets.value=data.attachments||[];baseline.value=JSON.stringify(form);void refreshPreviews()}
  }catch(e){if(!abort.signal.aborted)error.value=errorMessage(e)}finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})

async function save(status:'draft'|'published'){
  if(!await formRef.value?.validate().catch(()=>false))return
  saving.value=true
  try{
    const payload={...form,status}
    const response=route.params.id?await http.put<Post>(`/admin/posts/${route.params.id}`,payload):await http.post<Post>('/admin/posts',payload)
    form.status=status;baseline.value=JSON.stringify(form)
    ElMessage.success(status==='published'?'文章已发布':'草稿已保存')
    if(!route.params.id)await router.replace(`/articles/${response.data.id}/edit`)
  }catch(e){ElMessage.error(errorMessage(e))}finally{saving.value=false}
}

async function upload(event:Event){
  const target=event.target as HTMLInputElement,file=target.files?.[0];target.value=''
  if(!file)return
  if(!['image/jpeg','image/png','image/webp','application/pdf'].includes(file.type)||file.size<=0||file.size>10*1024*1024){ElMessage.error('支持 JPG、PNG、WebP、PDF，大小不超过 10MiB');return}
  if(assets.value.length>=50){ElMessage.error('每篇文章最多关联 50 个附件');return}
  uploading.value=true;progress.value=0
  try{
    const {data}=await http.post<{id:string;uploadUrl:string}>('/uploads/presign',{filename:file.name,contentType:file.type,size:file.size})
    // The COS request uses a separate Axios client with no application bearer header.
    await axios.put(data.uploadUrl,file,{headers:{'Content-Type':file.type},timeout:120000,onUploadProgress:event=>{progress.value=event.total?Math.round(event.loaded/event.total*95):0}})
    const completed=await http.post<Attachment>(`/uploads/${data.id}/complete`)
    assets.value.push(completed.data);form.content+=`\n\n[[asset:${completed.data.id}]]\n`
    progress.value=100;await refreshPreviews();ElMessage.success('附件已确认并插入正文')
  }catch(e){ElMessage.error(errorMessage(e))}finally{uploading.value=false}
}
function insert(text:string){form.content+=`\n${text}\n`}
onBeforeRouteLeave(async()=>{if(!dirty.value||saving.value)return true;try{await ElMessageBox.confirm('文章有尚未保存的修改，确定离开？','未保存的修改',{confirmButtonText:'离开',cancelButtonText:'继续编辑',type:'warning'});return true}catch{return false}})
function beforeUnload(event:BeforeUnloadEvent){if(dirty.value){event.preventDefault();event.returnValue=''}}
window.addEventListener('beforeunload',beforeUnload)
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload))
</script>
<template><section v-loading="loading"><div class="page-heading"><div><p class="section-kicker">WRITE YOUR STORY</p><h1>{{route.params.id?'继续这篇故事':'新的一页，从这里开始'}}</h1><p>Markdown 写作，支持私有图片与 PDF 附件。</p></div><div class="editor-actions"><el-button :icon="Document" :loading="saving" :disabled="loading||!!error||uploading" @click="save('draft')">保存草稿</el-button><el-button type="primary" :icon="Check" :loading="saving" :disabled="loading||!!error||uploading" @click="save('published')">{{form.status==='published'?'保存并发布':'发布文章'}}</el-button></div></div><el-alert v-if="error" :title="error" type="error" show-icon :closable="false"/><el-form v-else ref="formRef" :model="form" :rules="rules" label-position="top"><el-card shadow="never" class="editor-info"><el-form-item label="文章标题" prop="title"><el-input v-model="form.title" maxlength="180" show-word-limit placeholder="给这篇故事起一个名字" size="large"/></el-form-item><div class="editor-info-row"><el-form-item label="文章分类" prop="category"><el-input v-model="form.category" maxlength="60"/></el-form-item><el-form-item label="摘要" prop="summary"><el-input v-model="form.summary" maxlength="500" show-word-limit placeholder="用一两句话，邀请读者走进正文"/></el-form-item></div></el-card><div class="editor-grid"><el-card shadow="never"><template #header><div class="card-heading"><span>Markdown 正文</span><div><el-button text size="small" @click="insert('## 小标题')">标题</el-button><el-button text size="small" @click="insert('> 一段引用')">引用</el-button><el-button text size="small" :icon="Upload" :loading="uploading" @click="fileInput?.click()">上传附件</el-button></div></div></template><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden @change="upload"/><el-progress v-if="uploading" :percentage="progress" class="upload-progress"/><el-form-item prop="content" class="content-field"><el-input v-model="form.content" type="textarea" :autosize="{minRows:22,maxRows:40}" maxlength="200000" placeholder="# 故事的开头&#10;&#10;写下此刻的想法…"/></el-form-item><p class="editor-help">JPG / PNG / WebP / PDF · 单个文件不超过 10MiB</p></el-card><el-card shadow="never"><template #header><div class="card-heading"><span>阅读预览</span><el-button text size="small" :icon="Refresh" @click="refreshPreviews">刷新附件预览</el-button></div></template><el-alert v-if="previewError" :title="previewError" type="warning" :closable="false"/><div v-if="form.content" class="markdown-body" v-html="html"></div><el-empty v-else description="写下第一个字，预览会在这里展开" :image-size="100"/></el-card></div></el-form></section></template>
