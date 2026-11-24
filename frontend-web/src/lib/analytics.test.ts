import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const requests = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./http', () => ({ http: requests }))

beforeEach(() => {
  vi.resetModules()
  history.replaceState(null, '', '/')
  localStorage.clear()
  delete window._hmt
  document.querySelector('#baidu-analytics')?.remove()
  requests.get.mockReset()
  requests.post.mockReset().mockResolvedValue({})
})
afterEach(() => vi.restoreAllMocks())

function firstPartyPaths() {
  return requests.post.mock.calls.map(([, body]) => body.path)
}

describe('consented pageview collection', () => {
  it('does not create a visitor, send events or load a third-party script before consent', async () => {
    const { track } = await import('./analytics')
    track('/posts/10?private=value#fragment')
    expect(requests.get).not.toHaveBeenCalled()
    expect(requests.post).not.toHaveBeenCalled()
    expect(localStorage.getItem('blog-visitor')).toBeNull()
    expect(window._hmt).toBeUndefined()
    expect(document.querySelector('#baidu-analytics')).toBeNull()
  })

  it('uses the actual deep-link path if consent arrives before the initial router callback', async () => {
    history.replaceState(null, '', '/posts/42?private=value#fragment')
    requests.get.mockResolvedValue({ data: { baiduId: 'a'.repeat(32) } })
    const { enableAnalytics } = await import('./analytics')
    await enableAnalytics()
    expect(firstPartyPaths()).toEqual(['/posts/42'])
    expect(window._hmt).toEqual([['_setAutoPageview', false], ['_trackPageview', '/posts/42']])
  })

  it('keeps each visited page exactly once while analytics configuration is still loading', async () => {
    let resolveConfig!: (value: { data: { baiduId: string } }) => void
    requests.get.mockReturnValue(new Promise(resolve => { resolveConfig = resolve }))
    vi.spyOn(document, 'referrer', 'get').mockReturnValue('https://referrer.example/search?private=value#fragment')
    const { enableAnalytics, track } = await import('./analytics')
    track('/posts/10?private=value#fragment')
    const initialization = enableAnalytics()
    track('/posts/11?private=another#fragment')
    resolveConfig({ data: { baiduId: 'a'.repeat(32) } })
    await initialization
    expect(firstPartyPaths()).toEqual(['/posts/10', '/posts/11'])
    expect(window._hmt).toEqual([
      ['_setAutoPageview', false], ['_trackPageview', '/posts/10'], ['_trackPageview', '/posts/11'],
    ])
    expect(document.querySelector<HTMLScriptElement>('#baidu-analytics')?.src)
      .toBe('https://hm.baidu.com/hm.js?' + 'a'.repeat(32))
    const bodies = requests.post.mock.calls.map(([, body]) => body)
    expect(bodies[0].visitorId).toBe(bodies[1].visitorId)
    expect(bodies[0].referrer).toBe('https://referrer.example')
    expect(JSON.stringify(bodies)).not.toContain('private')
  })

  it('records a return visit and does not treat all repeated paths as duplicates', async () => {
    requests.get.mockResolvedValue({ data: { baiduId: 'a'.repeat(32) } })
    const { enableAnalytics, track } = await import('./analytics')
    track('/posts/10')
    await enableAnalytics()
    track('/posts/11')
    track('/posts/10')
    expect(firstPartyPaths()).toEqual(['/posts/10', '/posts/11', '/posts/10'])
    expect(window._hmt?.filter(command => command[0] === '_trackPageview'))
      .toEqual([['_trackPageview', '/posts/10'], ['_trackPageview', '/posts/11'], ['_trackPageview', '/posts/10']])
  })

  it('enables once and keeps first-party collection when the public Baidu ID is invalid', async () => {
    requests.get.mockResolvedValue({ data: { baiduId: 'invalid-id' } })
    const { enableAnalytics, track } = await import('./analytics')
    await Promise.all([enableAnalytics(), enableAnalytics()])
    track('/posts/12')
    expect(requests.get).toHaveBeenCalledTimes(1)
    expect(firstPartyPaths()).toEqual(['/', '/posts/12'])
    expect(document.querySelector('#baidu-analytics')).toBeNull()
  })

  it('keeps collection after a configuration request fails without loading an invalid script', async () => {
    requests.get.mockRejectedValue(new Error('configuration unavailable'))
    const { enableAnalytics, track } = await import('./analytics')
    track('/posts/10')
    await enableAnalytics()
    track('/posts/11?private=value')
    expect(firstPartyPaths()).toEqual(['/posts/10', '/posts/11'])
    expect(document.querySelector('#baidu-analytics')).toBeNull()
    expect(window._hmt).toBeUndefined()
  })
})
