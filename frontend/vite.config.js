import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// =====================================================
// Agnes AI Platform 前端 Vite 配置
// - 将 /api 请求代理到后端 http://localhost:8000
// - 开发模式下端口 5173
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
    port: 5173,
    open: true,
    proxy: {
      // 所有 /api 请求转发给后端 FastAPI
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      },
      // 健康检查接口也走代理
      '/health': {
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
        manualChunks: {
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'axios': ['axios']
        }
      }
    }
  }
})
