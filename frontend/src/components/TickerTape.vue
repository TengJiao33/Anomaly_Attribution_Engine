<template>
  <div class="ticker-tape">
     <div class="ticker-prefix">
         系统事件流:
     </div>
     <div class="ticker-view" ref="tickerContent">
         <div class="ticker-strip" :style="{ transform: `translateX(${scrollPos}px)` }">
             <span v-for="(msg, i) in displayMessages" :key="i" class="t-msg" :style="{ color: getColor(msg.type) }">
                 <span class="t-time">[{{ msg.time }}]</span> {{ msg.message }}
             </span>
         </div>
     </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'

const props = defineProps<{
  events: any[]
}>()

const scrollPos = ref(0)
let animationId: number

// 将后端事件转换为展示消息
const displayMessages = computed(() => {
    if (props.events.length === 0) {
        return [
            { time: '...', type: 'system', message: '等待系统事件...' }
        ]
    }
    return props.events.slice(-15)  // 展示最近 15 条
})

const getColor = (type: string): string => {
    const colorMap: Record<string, string> = {
        'system': 'var(--text-dim)',
        'replay': 'var(--accent-color)',
        'anomaly': 'var(--down-color)',
        'alignment': 'var(--up-color)',
        'llm': '#58a6ff',
    }
    return colorMap[type] || 'var(--text-dim)'
}

const animate = () => {
    scrollPos.value -= 1.2; 
    const totalWidth = displayMessages.value.length * 350
    if (scrollPos.value < -totalWidth) scrollPos.value = 800; 
    animationId = requestAnimationFrame(animate)
}

onMounted(() => {
    scrollPos.value = 800;
    animate()
})

onUnmounted(() => { cancelAnimationFrame(animationId) })

// 当有新事件时重置滚动位置
watch(() => props.events.length, () => {
    scrollPos.value = 800
})
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
    border-radius: 4px;
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
