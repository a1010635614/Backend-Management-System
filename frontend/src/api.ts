export async function api(path:string, init:RequestInit={}) {
  const headers=new Headers(init.headers)
  if(init.body) headers.set('Content-Type','application/json')
  const token=sessionStorage.getItem('token')
  if(token) headers.set('Authorization',`Bearer ${token}`)
  const response=await fetch(`/api${path}`,{...init,headers})
  if(!response.ok){const data=await response.json().catch(()=>({detail:'请求失败'}));throw new Error(typeof data.detail==='string'?data.detail:`请求失败 (${response.status})`)}
  return response.status===204?null:response.json()
}
