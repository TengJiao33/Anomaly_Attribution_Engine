# 异动雷达: 极速归因前端大屏 (Frontend)

本目录为“盘中异动极速归因聚合引擎”的前端视觉交互层。

与传统的“小清新”C端页面不同，本前端严格遵循**专业金融投研终端（如 Bloomberg, Wind 极速版）**的设计哲学。摒弃了花哨的三维动画与过度渲染，将屏幕空间最大化留给“高频交易图表”与“瞬时异动归因报告”。

## 技术栈与核心依赖
*   **Vue 3 + Composition API** ( `<script setup>`) + **TypeScript**
*   **Vite** (提供极速的模块热更与构建)
*   **图表渲染**: 计划采用金融级 Lightweight Charts / ECharts, 提供平滑、高帧率的百万级数据点缩放平移交互，以及异动锚点标注。

## 运行与构建
```bash
# 依赖安装
npm install

# 启动本地开发服务器
npm run dev

# 生产环境构建
npm run build
```
