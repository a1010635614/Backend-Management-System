import { http } from './http'

declare global { interface Window { _hmt?: unknown[][] } }
let enabled = false
let lastPath = '/'
export function track(path: string) {
  lastPath = path.split('?')[0]!.split('#')[0]!
  if (!enabled) return
  let visitor = localStorage.getItem('blog-visitor')
  if (!visitor) { visitor = crypto.randomUUID(); localStorage.setItem('blog-visitor', visitor) }
  window._hmt?.push(['_trackPageview', lastPath])
  void http.post('/analytics/events', { event: 'pageview', path: lastPath, visitorId: visitor,
    referrer: document.referrer ? new URL(document.referrer).origin : null }).catch(() => {})
}
export async function enableAnalytics() {
  if (enabled) return
  enabled = true
  try {
    const { data } = await http.get<{baiduId: string}>('/public/config')
    if (enabled && /^[a-f0-9]{32}$/i.test(data.baiduId)) {
      window._hmt = window._hmt || []
      window._hmt.push(['_setAutoPageview', false])
      const script = document.createElement('script')
      script.id = 'baidu-analytics'; script.async = true
      script.src = `https://hm.baidu.com/hm.js?${data.baiduId}`
      document.head.appendChild(script)
    }
  } catch { /* First-party analytics can work if the Baidu service is unavailable. */ }
  if (enabled) track(lastPath)
}
