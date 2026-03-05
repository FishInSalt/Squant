import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'

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
        // Buffer the full upstream response before forwarding to the browser.
        // Prevents ERR_CONTENT_LENGTH_MISMATCH / ERR_INCOMPLETE_CHUNKED_ENCODING
        // caused by http-proxy forwarding partial data when the connection to
        // uvicorn drops mid-transfer (intermittent in DevContainer networking).
        selfHandleResponse: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes, _req, res) => {
            const chunks: Buffer[] = []
            proxyRes.on('data', (chunk: Buffer) => chunks.push(chunk))
            proxyRes.on('end', () => {
              const body = Buffer.concat(chunks)
              const headers = { ...proxyRes.headers }
              delete headers['transfer-encoding']
              headers['content-length'] = String(body.length)
              res.writeHead(proxyRes.statusCode!, headers)
              res.end(body)
            })
            proxyRes.on('error', () => {
              if (!res.headersSent) res.writeHead(502)
              res.end()
            })
          })
          proxy.on('error', (_err, _req, res: any) => {
            if (res.writeHead && !res.headersSent) {
              res.writeHead(502)
              res.end()
            }
          })
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
        additionalData: `@use "@/styles/variables.scss" as *;`,
      },
    },
  },
})
