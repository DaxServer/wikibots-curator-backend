import { fileURLToPath, URL } from 'node:url'
import type { PluginOption } from 'vite'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import Components from 'unplugin-vue-components/vite'
import { PrimeVueResolver } from "@primevue/auto-import-resolver"
import tailwindcss from '@tailwindcss/vite'

// Define environment variables type
type EnvVariables = {
    VITE_API_KEY?: string;
    [key: string]: string | undefined;
}

// https://vite.dev/config/
export default defineConfig(({ mode }): import('vite').UserConfig => {
    // Load env file based on `mode` in the current directory
    const env: EnvVariables = loadEnv(mode, process.cwd(), '');

    // Configure proxy with proper types
    const configureProxy = (proxy: {
        on: (event: 'proxyReq', handler: (proxyReq: {
            setHeader: (name: string, value: string) => void;
        }) => void) => void;
    }): void => {
        proxy.on('proxyReq', (proxyReq) => {
            // Add API key to the request headers
            if (env.VITE_API_KEY) {
                proxyReq.setHeader('X-API-KEY', env.VITE_API_KEY);
            }
        });
    };

    return {
        plugins: [
            vue(),
            vueDevTools(),
            Components({
                resolvers: [
                    PrimeVueResolver()
                ]
            }),
            tailwindcss(),
        ] as PluginOption[],
        resolve: {
            alias: {
                '@': fileURLToPath(new URL('./src', import.meta.url))
            },
        },
        server: {
            proxy: {
                '/api/harbor': {
                    target: 'http://localhost:8000',
                    changeOrigin: true,
                },
                '/api': {
                    target: 'https://curator.toolforge.org',
                    changeOrigin: true,
                    configure: configureProxy
                },
            }
        }
    };
});
