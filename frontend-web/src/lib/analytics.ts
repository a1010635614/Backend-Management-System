import { http } from './http'

declare global { interface Window { _hmt?: unknown[][] } }
let enabled = false
let lastPath = window.location.pathname || '/'
let baiduState: 'pending' | 'enabled' | 'disabled' = 'pending'
let pendingPageviews: string[] = []
export function track(path: string) {
  lastPath = path.split('?')[0]!.split('#')[0]!
  if (!enabled) return
  let visitor = localStorage.getItem('blog-visitor')
  if (!visitor) { visitor = crypto.randomUUID(); localStorage.setItem('blog-visitor', visitor) }
  if (baiduState === 'pending') pendingPageviews.push(lastPath)
  else if (baiduState === 'enabled') window._hmt?.push(['_trackPageview', lastPath])
  void http.post('/analytics/events', { event: 'pageview', path: lastPath, visitorId: visitor,
    referrer: document.referrer ? new URL(document.referrer).origin : null }).catch(() => {})
}
export async function enableAnalytics() {
  if (enabled) return
  enabled = true
  // Count the consented current page now; configuration must not replay a later route.
  track(lastPath)
  try {
    const { data } = await http.get<{baiduId: string}>('/public/config')
    if (/^[a-f0-9]{32}$/i.test(data.baiduId)) {
      window._hmt = window._hmt || []
      window._hmt.push(['_setAutoPageview', false])
      baiduState = 'enabled'
      for (const path of pendingPageviews) window._hmt.push(['_trackPageview', path])
      pendingPageviews = []
      const script = document.createElement('script')
      script.id = 'baidu-analytics'; script.async = true
      script.src = `https://hm.baidu.com/hm.js?${data.baiduId}`
      document.head.appendChild(script)
    } else {
      baiduState = 'disabled'
      pendingPageviews = []
    }
  } catch {
    // First-party collection remains available without a third-party script.
    baiduState = 'disabled'
    pendingPageviews = []
  }
}
