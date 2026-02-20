<template>
  <div class="terminal-root">
    <!-- 系统头部 -->
    <header class="sys-header">
      <div class="sys-title">
        <span class="blinker"></span> 异动雷达 · 盘中对齐与归因引擎
      </div>
      <div class="sys-controls">
        <!-- 模式切换：回放 / 实盘 -->
        <div class="mode-switch">
          <button 
            class="mode-btn" 
            :class="{ active: !isLiveMode }" 
            @click="setMode(false)"
          >
            历史回放
          </button>
          <button 
            class="mode-btn live-btn" 
            :class="{ active: isLiveMode }" 
            @click="setMode(true)"
          >
            <span class="live-dot" v-show="isLiveMode"></span>
            ⚡实盘(Live)
          </button>
        </div>

        <span class="label" v-show="!isLiveMode">回放案例:</span>
        <select v-model="currentCaseId" @change="switchCase" class="raw-select" v-show="!isLiveMode">
          <option v-for="c in availableCases" :key="c.case_id" :value="c.case_id">
            {{ c.symbol_name }} ({{ c.symbol }}) — {{ c.anomaly_type }}
          </option>
        </select>

        <!-- 回放控制器 -->
        <div class="replay-controls" v-show="!isLiveMode">
          <button class="ctrl-btn" @click="togglePause" :title="isPaused ? '继续' : '暂停'">
            {{ isPaused ? '▶' : '⏸' }}
          </button>
          <select v-model="playbackSpeed" @change="changeSpeed" class="speed-select">
            <option :value="0.5">0.5x</option>
            <option :value="1">1x</option>
            <option :value="2">2x</option>
            <option :value="5">5x</option>
          </select>
        </div>

        <div class="conn-status" :class="{ 'online': wsConnected }">
          <span class="status-dot"></span> {{ wsConnected ? '毫秒级硬链接口 : 已连接' : '底层接口 : 断开' }}
        </div>
      </div>
    </header>

    <!-- 高频日志带 -->
    <TickerTape :events="systemEvents" />

    <!-- 核心两栏投研网格 -->
    <main class="terminal-grid">
        <!-- 左侧：K线行情 -->
        <div class="term-panel kline-area">
          <div class="panel-header">
            {{ isLiveMode ? '全市场实盘监听雷达 // 实时模拟推演' : `历史复盘推演视图 // ${symbolName}` }}
          </div>
          <div class="panel-body">
            <ChartBoard
              :data="chartData"
              :symbolName="symbolName"
              :highlightedAnomalyIndex="highlightedAnomalyIndex"
              @anomaly-click="onAnomalyClickFromChart"
            />
          </div>
        </div>

        <!-- 右侧：大模型归因流（可滚动） -->
        <div class="term-panel attr-area">
          <div class="panel-header alert-header">
             ⚡ 全域时序瞬时归因瀑布流 (LLM Extraction Feed)
          </div>
          <div class="panel-body raw-spool">
            <AttributionFeed
              :data="anomalyData"
              :highlightedIndex="highlightedFeedIndex"
              @card-click="onCardClickFromFeed"
            />
          </div>
        </div>
    </main>

    <!-- 系统尾部（动态指标） -->
    <footer class="sys-footer">
       <span>WS推送: <span class="metric">{{ metrics.total_ticks_pushed || 0 }}</span> ticks</span> |
       <span>异动检测: <span class="metric alert">{{ metrics.anomalies_detected || 0 }}</span></span> |
       <span>LLM调用: <span class="metric">{{ metrics.llm_calls || 0 }}</span> (缓存: {{ metrics.llm_cache_hits || 0 }})</span> |
       <span>缓存: <span class="metric">{{ metrics.cache_mode || '...' }}</span></span> |
       <span>延迟: <span class="metric">{{ metrics.avg_llm_latency_ms || 0 }}ms</span></span> |
       <span style="color:var(--text-dim)">引擎 v4.0.0 · 多信号贝叶斯融合</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import ChartBoard from './components/ChartBoard.vue'
import AttributionFeed from './components/AttributionFeed.vue'
import TickerTape from './components/TickerTape.vue'

const API_BASE = ''

interface CaseInfo {
  case_id: string
  symbol: string
  symbol_name: string
  case_date: string
  description: string
  anomaly_type: string
  tick_count: number
  news_count: number
}

const isLiveMode = ref(false)
const currentCaseId = ref('')
const availableCases = ref<CaseInfo[]>([])
const chartData = ref<any[]>([])
const symbolName = ref('')
const systemEvents = ref<any[]>([])
const metrics = ref<any>({})

// K线 ↔ 归因联动状态
const highlightedAnomalyIndex = ref<number | null>(null)
const highlightedFeedIndex = ref<number | null>(null)

// 回放控制
const isPaused = ref(false)
const playbackSpeed = ref(1)

let ws: WebSocket | null = null
const wsConnected = ref(false)
let metricsTimer: number | null = null
let eventsTimer: number | null = null
let tickCounter = 0

// 独立的异动数据流，避免每次 chartData 变化都产生新的数组引用
const anomalyData = ref<any[]>([])

// ===== K线 ↔ 归因联动 ===== //
const onAnomalyClickFromChart = (dataIndex: number) => {
    // 在 anomalyData 中找到对应的索引
    const anomalyItem = chartData.value[dataIndex]
    if (!anomalyItem) return
    const feedIdx = anomalyData.value.findIndex(item => item._uid === anomalyItem._uid)
    if (feedIdx >= 0) {
        highlightedFeedIndex.value = feedIdx
        // 3秒后清除高亮
        setTimeout(() => { highlightedFeedIndex.value = null }, 3000)
    }
}

const onCardClickFromFeed = (feedIndex: number) => {
    // 从异动列表的索引反查 chartData 的索引
    const anomalyItem = anomalyData.value[feedIndex]
    if (!anomalyItem) return
    const chartIdx = chartData.value.findIndex(item => item._uid === anomalyItem._uid)
    if (chartIdx >= 0) {
        highlightedAnomalyIndex.value = chartIdx
        setTimeout(() => { highlightedAnomalyIndex.value = null }, 3000)
    }
}

// ===== 回放控制 ===== //
const togglePause = () => {
    isPaused.value = !isPaused.value
    sendControl(isPaused.value ? 'pause' : 'resume')
}

const changeSpeed = () => {
    sendControl('set_speed', playbackSpeed.value)
}

const sendControl = (action: string, value?: number) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action, value: value ?? null }))
    }
}

// 从后端动态加载可用案例列表
const loadAvailableCases = async () => {
    try {
        const res = await axios.get(`${API_BASE}/api/available_cases`)
        availableCases.value = res.data
        if (availableCases.value.length > 0 && !currentCaseId.value) {
            const firstCase = availableCases.value[0]
            if (firstCase) currentCaseId.value = firstCase.case_id
        }
    } catch (err) {
        console.error("加载案例列表失败:", err)
    }
}

// 定期刷新系统指标
const refreshMetrics = async () => {
    try {
        const res = await axios.get(`${API_BASE}/api/system_status`)
        metrics.value = res.data
    } catch (e) { /* 静默失败 */ }
}

// 定期刷新系统事件
const refreshEvents = async () => {
    try {
        const res = await axios.get(`${API_BASE}/api/system_events`)
        systemEvents.value = res.data
    } catch (e) { /* 静默失败 */ }
}

const setMode = (toLive: boolean) => {
    if (isLiveMode.value === toLive) return
    isLiveMode.value = toLive
    chartData.value = []
    anomalyData.value = []
    setupWebSocket()
}

const setupWebSocket = () => {
    if (ws) ws.close()

    if (!isLiveMode.value) {
        const currentCase = availableCases.value.find(c => c.case_id === currentCaseId.value)
        symbolName.value = currentCase ? currentCase.symbol_name : ''
    } else {
        symbolName.value = 'MOCK_LIVE_STREAM'
    }

    // 重置联动状态
    highlightedAnomalyIndex.value = null
    highlightedFeedIndex.value = null
    isPaused.value = false
    playbackSpeed.value = 1
    tickCounter = 0
    anomalyData.value = []

    // WebSocket 推送完整回放数据，不再通过 HTTP 加载初始快照
    // （避免 HTTP + WebSocket 数据竞态导致图表闪烁和 K 线消失）

    // 建立 WebSocket 连接
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = isLiveMode.value 
        ? `${wsProtocol}//${window.location.host}/ws/live_feed`
        : `${wsProtocol}//${window.location.host}/ws/alignment_feed/${currentCaseId.value}`
        
    ws = new WebSocket(wsUrl)
    ws.onopen = () => { wsConnected.value = true; }
    ws.onmessage = (event) => {
        try {
            const newTick = JSON.parse(event.data)
            newTick._uid = `tick-${tickCounter++}`
            chartData.value.push(newTick)
            if (chartData.value.length > 200) chartData.value.shift()
            
            // 单独维护 anomalyData 数组，避免 computed 重新计算导致所有旧元素被 Vue 误以为是全新节点
            if (newTick.hasAnomaly && newTick.anomalyDetails) {
                anomalyData.value.push(newTick)
                // 限制最大归因卡片数量
                if (anomalyData.value.length > 100) anomalyData.value.shift()
            }
        } catch (e) {
            console.error("WS_PARSE_ERR", e)
        }
    }
    ws.onclose = () => { wsConnected.value = false; }
    ws.onerror = (err) => { console.error("WS_ERR", err) }
}

const switchCase = () => { chartData.value = []; anomalyData.value = []; setupWebSocket() }

onMounted(async () => {
    await loadAvailableCases()
    if (currentCaseId.value) {
        setupWebSocket()
    }
    // 启动定时刷新
    metricsTimer = window.setInterval(refreshMetrics, 2000)
    eventsTimer = window.setInterval(refreshEvents, 1500)
})

onUnmounted(() => {
    if (ws) ws.close()
    if (metricsTimer) clearInterval(metricsTimer)
    if (eventsTimer) clearInterval(eventsTimer)
})
</script>

<style scoped>
.terminal-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: var(--bg-color);
  padding: 8px;
  gap: 6px;
}

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

/* 模式切换按钮 */
.mode-switch {
  display: flex;
  background-color: rgba(255,255,255,0.05);
  border-radius: 6px;
  padding: 2px;
  border: 1px solid var(--border-color);
}

.mode-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: var(--font-sans);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}

.mode-btn:hover {
  color: var(--text-main);
}

.mode-btn.active {
  background-color: var(--panel-border);
  color: var(--text-main);
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}

.mode-btn.live-btn.active {
  background-color: rgba(248, 81, 73, 0.15);
  color: var(--down-color);
  border: 1px solid rgba(248, 81, 73, 0.3);
}

.live-dot {
  width: 6px;
  height: 6px;
  background-color: var(--down-color);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--down-color);
  animation: live-blink 1s ease-in-out infinite alternate;
}

@keyframes live-blink {
  from { opacity: 0.4; }
  to { opacity: 1; transform: scale(1.2); }
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
  max-width: 420px;
}
.raw-select:focus {
  border-color: var(--accent-color);
}

/* 回放控制器 */
.replay-controls {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ctrl-btn {
  background: var(--bg-color);
  border: 1px solid var(--border-color);
  color: var(--text-main);
  width: 28px;
  height: 28px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.ctrl-btn:hover {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.speed-select {
  background-color: var(--bg-color);
  color: var(--text-main);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 2px 4px;
  font-size: 11px;
  font-family: var(--font-mono);
  cursor: pointer;
  outline: none;
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
  grid-template-rows: minmax(0, 1fr);  /* 关键：限制行高不超过可用空间 */
  gap: 8px;
  overflow: hidden;
  min-height: 0;  /* flex 子元素必须有 min-height:0 才能缩小 */
}

.term-panel {
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  background-color: var(--panel-bg);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  overflow: hidden;     /* 防止子内容撑大面板 */
  min-height: 0;        /* flex 子元素必须有 min-height:0 */
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
  background-color: rgba(248, 81, 73, 0.05);
  font-weight: 600;
}

.panel-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.raw-spool {
  overflow-y: auto;
  min-height: 0;  /* 配合 flex:1 使内容可滚动 */
}

/* 尾部 */
.sys-footer {
  font-family: var(--font-mono);
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text-dim);
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  background-color: var(--panel-bg);
}

.metric {
  color: var(--up-color);
  font-weight: 600;
}

.metric.alert {
  color: var(--down-color);
}
</style>
