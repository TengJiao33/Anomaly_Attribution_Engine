<template>
  <div class="terminal-root">
    <!-- 系统头部 -->
    <header class="sys-header">
      <div class="sys-title">
        <span class="blinker"></span> 异动雷达 · 盘中对齐与归因引擎
      </div>
      <div class="sys-controls">
        <span class="label">当前席位标的:</span>
        <select v-model="currentSymbol" @change="switchSymbol" class="raw-select">
          <option value="sh.600519">贵州茅台 (SH.600519)</option>
          <option value="sz.002594">比亚迪 (SZ.002594)</option>
          <option value="crypto.btc">比特币 (CRYPTO.BTC)</option>
        </select>
        <div class="conn-status" :class="{ 'online': wsConnected }">
          <span class="status-dot"></span> {{ wsConnected ? '毫秒级硬链接口 : 已连接' : '底层接口 : 断开' }}
        </div>
      </div>
    </header>

    <!-- 高频日志带 -->
    <TickerTape />

    <!-- 核心两栏投研网格 -->
    <main class="terminal-grid">
        <!-- 左侧：K线行情 -->
        <div class="term-panel kline-area">
          <div class="panel-header">实盘高频推演视图 // {{ symbolName }}</div>
          <div class="panel-body">
            <ChartBoard :data="chartData" :symbolName="symbolName" />
          </div>
        </div>

        <!-- 右侧：大模型归因流 -->
        <div class="term-panel attr-area">
          <div class="panel-header alert-header">
             ⚡ 全域时序瞬时归因瀑布流 (LLM Extraction Feed)
          </div>
          <div class="panel-body raw-spool">
            <AttributionFeed :data="anomalyData" />
          </div>
        </div>
    </main>
    
    <!-- 系统尾部 -->
    <footer class="sys-footer">
       <span>节点负载: 12%</span> | 
       <span>内存分配: 4.1 GB</span> | 
       <span>LLM 状态: <span style="color:var(--up-color)">待命中</span></span> | 
       <span style="color:var(--text-dim)">量化核心 v2.0.1_STABLE</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import axios from 'axios'
import ChartBoard from './components/ChartBoard.vue'
import AttributionFeed from './components/AttributionFeed.vue'
import TickerTape from './components/TickerTape.vue'

const currentSymbol = ref('sh.600519')
const chartData = ref<any[]>([])
const symbolName = ref('')

let ws: WebSocket | null = null
const wsConnected = ref(false)

const getSymbolName = (sym: string) => {
    return {"sh.600519": "贵州茅台", "sz.002594": "比亚迪", "crypto.btc": "比特币"}[sym] || sym;
}

const anomalyData = computed(() => {
    return chartData.value.filter(item => item.hasAnomaly && item.anomalyDetails)
})

const setupWebSocket = () => {
    if (ws) ws.close()
    
    symbolName.value = getSymbolName(currentSymbol.value)
    
    axios.get(`http://localhost:8000/api/alignment_data/${currentSymbol.value}`)
      .then(res => {
         if (res.data) chartData.value = res.data.data
      }).catch(err => console.error("INIT_ERR:", err))
    
    ws = new WebSocket(`ws://localhost:8000/ws/alignment_feed/${currentSymbol.value}`)
    ws.onopen = () => { wsConnected.value = true; }
    ws.onmessage = (event) => {
        try {
            const newTick = JSON.parse(event.data)
            chartData.value.push(newTick)
            if (chartData.value.length > 200) chartData.value.shift()
        } catch (e) {
            console.error("WS_PARSE_ERR", e)
        }
    }
    ws.onclose = () => { wsConnected.value = false; }
    ws.onerror = (err) => { console.error("WS_ERR", err) }
}

const switchSymbol = () => { chartData.value = []; setupWebSocket() }
onMounted(() => { setupWebSocket() })
onUnmounted(() => { if (ws) ws.close() })
</script>

<style scoped>
.terminal-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: var(--bg-color);
  padding: 8px; /* 恢复适当边距 */
  gap: 6px;
}

/* 头部 */
.sys-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  padding: 8px 16px;
  background-color: var(--panel-bg);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.sys-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 8px;
}

.blinker {
  display: inline-block;
  width: 6px;
  height: 14px;
  background-color: var(--accent-color);
  animation: blink 1s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

.sys-controls {
  display: flex;
  align-items: center;
  gap: 15px;
  font-size: 13px;
}

.label {
  color: var(--text-dim);
}

.raw-select {
  background-color: var(--bg-color);
  color: var(--text-main);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-family: var(--font-sans);
  padding: 4px 8px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}
.raw-select:focus {
  border-color: var(--accent-color);
}

.conn-status { 
  display: flex; 
  align-items: center; 
  gap: 6px;
  color: var(--down-color); 
  font-family: var(--font-mono);
  font-size: 12px;
}
.conn-status.online { color: var(--up-color); }

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: currentColor;
  box-shadow: 0 0 6px currentColor;
}

/* 主网格 */
.terminal-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 7fr 3fr;
  gap: 8px;
  overflow: hidden;
}

.term-panel {
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  background-color: var(--panel-bg);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.panel-header {
  border-bottom: 1px solid var(--border-color);
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-dim);
  background-color: rgba(255,255,255,0.02);
  font-weight: 500;
}

.alert-header {
  color: var(--down-color);
  border-bottom: 1px solid rgba(248, 81, 73, 0.2);
  background-color: rgba(248, 81, 73, 0.05); /* 柔和红底 */
  font-weight: 600;
}

.panel-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 尾部 */
.sys-footer {
  font-family: var(--font-mono);
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text-dim);
  display: flex;
  gap: 15px;
  justify-content: flex-end;
}
</style>
