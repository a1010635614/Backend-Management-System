declare global { interface Window { _hmt?: unknown[][] } }
let currentPath='/',enabled=false,loaded=false
export async function enableAnalytics(){
  localStorage.setItem('analytics-consent','yes');enabled=true
  try{
    const config=await fetch('/api/public/config').then(r=>{if(!r.ok)throw Error();return r.json()})
    if(!loaded&&/^[a-f0-9]{32}$/.test(config.baiduId)){
      loaded=true;window._hmt=window._hmt||[]
      window._hmt.push(['_setAutoPageview',false])
      const script=document.createElement('script');script.src=`https://hm.baidu.com/hm.js?${config.baiduId}`;document.head.appendChild(script)
    }
  }catch{/* 一方统计仍可独立工作 */}
  track(currentPath)
}
export function track(path:string){
  currentPath=path
  if(!enabled)return
  let visitorId=localStorage.getItem('visitor-id')
  if(!visitorId){visitorId=crypto.randomUUID();localStorage.setItem('visitor-id',visitorId)}
  // 不上传查询参数、hash 或完整 referrer，避免把令牌等信息带入统计。
  window._hmt?.push(['_trackPageview',path])
  void fetch('/api/analytics/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event:'pageview',path,visitorId}),keepalive:true}).catch(()=>{})
}
