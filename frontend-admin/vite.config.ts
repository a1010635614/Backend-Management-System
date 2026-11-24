import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    base: '/admin/', plugins: [vue(), Components({dts:mode==='test'?false:'src/components.d.ts',resolvers:[ElementPlusResolver()]})],
    server: { host: '127.0.0.1', port: 5174, strictPort: true,
      proxy: { '/api': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } } },
    test: { environment: 'jsdom', server: { deps: { inline: ['element-plus'] } } },
  }
})
