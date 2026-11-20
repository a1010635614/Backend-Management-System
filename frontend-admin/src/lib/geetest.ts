type Proof = Record<string, string>
interface Captcha {
  onReady(callback: () => void): Captcha
  onSuccess(callback: () => void): Captcha
  onClose(callback: () => void): Captcha
  onError(callback: () => void): Captcha
  getValidate(): Proof | false
  showCaptcha(): void
  destroy(): void
}
declare global { interface Window { initGeetest4?: (options: { captchaId: string; product: 'bind' }, callback: (captcha: Captcha) => void) => void } }
let sdk: Promise<void> | null = null
function loadSdk(): Promise<void> {
  if (window.initGeetest4) return Promise.resolve()
  if (sdk) return sdk
  sdk = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://static.geetest.com/v4/gt4.js'
    script.async = true
    script.onload = () => window.initGeetest4 ? resolve() : reject(new Error('行为验证初始化失败'))
    script.onerror = () => { sdk = null; script.remove(); reject(new Error('行为验证加载失败，请重试')) }
    document.head.appendChild(script)
  })
  return sdk
}
export async function challenge(captchaId: string, required: boolean): Promise<Proof> {
  if (!required) return {}
  if (!captchaId) throw new Error('行为验证尚未配置')
  await loadSdk()
  return new Promise((resolve, reject) => {
    let instance: Captcha | undefined
    let settled = false
    const timer = window.setTimeout(() => finish(), 120000)
    const finish = (proof?: Proof) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      instance?.destroy()
      proof ? resolve(proof) : reject(new Error('行为验证未完成，请重试'))
    }
    window.initGeetest4!({ captchaId, product: 'bind' }, captcha => {
      instance = captcha
      captcha.onReady(() => captcha.showCaptcha())
        .onSuccess(() => finish(captcha.getValidate() || undefined))
        .onClose(() => finish())
        .onError(() => finish())
    })
  })
}
