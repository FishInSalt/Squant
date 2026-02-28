import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import AutoImport from 'unplugin-auto-import/vite';
import Components from 'unplugin-vue-components/vite';
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';
import path from 'path';
export default defineConfig({
    plugins: [
        vue(),
        AutoImport({
            imports: ['vue', 'vue-router', 'pinia'],
            resolvers: [ElementPlusResolver()],
            dts: 'src/auto-imports.d.ts',
        }),
        Components({
            resolvers: [ElementPlusResolver()],
            dts: 'src/components.d.ts',
        }),
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'src'),
        },
    },
    server: {
        host: true,
        port: 5175,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                // Strip upstream Content-Length so Node.js http server uses chunked
                // transfer encoding. Prevents ERR_CONTENT_LENGTH_MISMATCH caused by
                // http-proxy forwarding Content-Length but delivering bytes via chunks.
                configure: function (proxy) {
                    proxy.on('proxyRes', function (proxyRes) {
                        delete proxyRes.headers['content-length'];
                    });
                },
            },
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
            },
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                additionalData: "@use \"@/styles/variables.scss\" as *;",
            },
        },
    },
});
