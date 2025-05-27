import { fileURLToPath, URL } from 'node:url'
import type { PluginOption } from 'vite'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'
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

    // Define proxy configuration with proper types
    const proxy: Record<string, string | ProxyOptions> = {
        // Toolforge API proxy
        '/curator-api': {
            target: 'https://curator.toolforge.org',
            changeOrigin: true,
            rewrite: (path: string) => path.replace(/^\/curator-api/, ''),
            configure: configureProxy
        },
        // Harbor API proxy
        '/harbor-api': {
            target: 'https://tools-harbor.wmcloud.org',
            changeOrigin: true,
            rewrite: (path: string) => path.replace(/^\/harbor-api/, '/api/v2.0')
        }
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
            proxy
        }
    };
});
