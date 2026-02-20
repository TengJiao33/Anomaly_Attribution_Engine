<template>
  <div class="ticker-tape">
     <div class="ticker-prefix">
         系统底座日志:
     </div>
     <div class="ticker-view" ref="tickerContent">
         <div class="ticker-strip" :style="{ transform: `translateX(${scrollPos}px)` }">
             <span v-for="(msg, i) in messages" :key="i" class="t-msg" :style="{ color: msg.color }">
                 <span class="t-time">[{{ msg.time }}]</span> {{ msg.text }}
             </span>
         </div>
     </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const messages = ref([
    { time: '初始化', text: '正在启动时序强制对齐引擎...', color: 'var(--text-dim)' },
    { time: '链路 1', text: '接入本地大语言模型推理核心', color: 'var(--text-dim)' },
    { time: '安全网', text: '市场噪音反制过滤：已激活', color: 'var(--up-color)' },
    { time: '监听中', text: '等待盘口异动级联发酵', color: 'var(--warning-color)' },
    { time: '状态', text: '系统全速在线', color: 'var(--up-color)' },
])

const scrollPos = ref(0)
let animationId: number

const animate = () => {
    scrollPos.value -= 1.5; 
    if (scrollPos.value < -1000) scrollPos.value = 800; 
    animationId = requestAnimationFrame(animate)
}

onMounted(() => {
    scrollPos.value = 800;
    animate()
})

onUnmounted(() => { cancelAnimationFrame(animationId) })
</script>

<style scoped>
.ticker-tape {
    height: 28px;
    border: 1px solid var(--panel-border);
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    overflow: hidden;
    background-color: var(--panel-bg);
    border-radius: 4px; /* 恢复一点护眼圆角 */
}

.ticker-prefix {
    padding: 0 12px;
    border-right: 1px solid var(--border-color);
    color: var(--text-dim);
    font-size: 12px;
    font-family: var(--font-sans);
    white-space: nowrap;
    background-color: var(--bg-color);
    height: 100%;
    display: flex;
    align-items: center;
}

.ticker-view {
    flex: 1;
    overflow: hidden;
    white-space: nowrap;
}

.ticker-strip {
    display: inline-flex;
    will-change: transform;
}

.t-msg {
    margin-right: 40px;
    font-size: 12px;
    font-family: var(--font-mono);
}

.t-time {
    color: var(--text-dim);
    margin-right: 6px;
}
</style>
