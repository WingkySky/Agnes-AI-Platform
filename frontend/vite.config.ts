import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// =====================================================
// Agnes AI Platform 前端 Vite 配置
// - 将 /api 请求代理到后端 http://localhost:8000
// - 开发模式下端口 5174
// =====================================================

export default defineConfig({
  plugins: [vue()],

  // 路径别名：@ 指向 src 目录
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },

  // 开发服务器配置
  server: {
    host: '0.0.0.0',
    port: 5174,
    open: true,
    proxy: {
      // 所有 /api 请求转发给后端 FastAPI
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        // SSE 流式响应需要禁用缓冲和压缩
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              // 禁用 Nginx/代理缓冲，确保 SSE 事件实时推送
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
              delete proxyRes.headers['content-length']
            }
          })
        },
      },
      // 健康检查接口也走代理
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 用户上传的头像等静态资源走后端服务
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 官方预设封面等种子静态资源走后端服务
      '/seed-assets': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },

  // 构建配置
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 按依赖拆分 chunk，降低单个文件体积
        // vite 8（rolldown）仅支持函数形式 manualChunks
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('element-plus') || id.includes('@element-plus/icons-vue')) {
            return 'element-plus'
          }
          if (/[\\/]node_modules[\\/](vue|vue-router|pinia|@vue)[\\/]/.test(id)) {
            return 'vue-vendor'
          }
          if (/[\\/]node_modules[\\/]axios[\\/]/.test(id)) {
            return 'axios'
          }
          return undefined
        }
      }
    }
  }
})
