import { fileURLToPath, URL } from 'node:url'
import type { PluginOption, UserConfig } from 'vite'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import Components from 'unplugin-vue-components/vite'
import { PrimeVueResolver } from '@primevue/auto-import-resolver'
import tailwindcss from '@tailwindcss/vite'

// Define environment variables type
type EnvVariables = {
  VITE_API_KEY?: string
  [key: string]: string | undefined
}

// https://vite.dev/config/
export default defineConfig(({ mode }): UserConfig => {
  // Load env file based on `mode` in the current directory
  const env: EnvVariables = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      vue(),
      vueDevTools(),
      Components({
        resolvers: [PrimeVueResolver()],
      }),
      tailwindcss(),
    ] as PluginOption[],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 8000,
      proxy: {
        '/auth': {
          target: 'http://localhost:8001',
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: 'https://curator.toolforge.org',
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              if (env.VITE_API_KEY) {
                proxyReq.setHeader('X-API-KEY', env.VITE_API_KEY)
              }
            })
          },
        },
      },
    },
  }
})
