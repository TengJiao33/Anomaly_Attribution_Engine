import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import viteCompression from 'vite-plugin-compression'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // gzip 压缩：对大型 GeoJSON 等静态资源效果显著（通常压缩比 70-80%）
    viteCompression({
      algorithm: 'gzip',
      threshold: 10240,   // 仅压缩 >10KB 的文件
      ext: '.gz',
    }),
  ],
})
