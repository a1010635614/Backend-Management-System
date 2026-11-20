<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {ElMessage} from 'element-plus'
import {http,errorMessage} from '../lib/http'
import type {Role} from '../lib/types'
import {useAuthStore} from '../stores/auth'
type Row={id:number;email:string;role:Role;is_active:boolean;createdAt:string}
const auth=useAuthStore(),items=ref<Row[]>([]),total=ref(0),page=ref(1),loading=ref(false),saving=ref<number|null>(null),error=ref('')
async function load(){loading.value=true;error.value='';try{const {data}=await http.get<{items:Row[];total:number}>('/admin/users',{params:{page:page.value,page_size:20}});items.value=data.items;total.value=data.total}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
async function save(id:number){const row=items.value.find(item=>item.id===id);if(!row)return;saving.value=row.id;try{await http.patch(`/admin/users/${row.id}`,{role:row.role,is_active:row.is_active});ElMessage.success('权限已更新，服务端即时生效')}catch(e){ElMessage.error(errorMessage(e));await load()}finally{saving.value=null}}
onMounted(()=>void load())
</script>
<template><section><div class="page-heading"><div><p class="section-kicker">ACCESS CONTROL</p><h1>用户与权限</h1><p>管理员可管理所有内容；编辑可管理自己的文章；读者仅访问前台。</p></div></div><el-alert v-if="error" :title="error" type="error" :closable="false"/><el-card shadow="never"><el-table v-loading="loading" :data="items" empty-text="暂无用户"><el-table-column prop="email" label="邮箱" min-width="240"/><el-table-column label="角色" width="160"><template #default="{row}"><el-select v-model="row.role" :disabled="row.id===auth.user?.id"><el-option label="管理员" value="admin"/><el-option label="编辑" value="editor"/><el-option label="读者" value="viewer"/></el-select></template></el-table-column><el-table-column label="账号启用" width="120"><template #default="{row}"><el-switch v-model="row.is_active" :disabled="row.id===auth.user?.id"/></template></el-table-column><el-table-column label="加入日期" width="140"><template #default="{row}">{{new Date(row.createdAt).toLocaleDateString('zh-CN')}}</template></el-table-column><el-table-column label="操作" width="100"><template #default="{row}"><el-button type="primary" link :loading="saving===row.id" :disabled="row.id===auth.user?.id" @click="save(row.id)">保存</el-button></template></el-table-column></el-table><el-pagination v-if="total>20" v-model:current-page="page" :total="total" :page-size="20" layout="total,prev,pager,next" class="table-pagination" @current-change="load"/></el-card><div class="permission-note">权限不仅控制菜单和动态路由，后端也会独立校验每一个管理请求。禁用的账号将无法继续使用现有 Token。</div></section></template>
