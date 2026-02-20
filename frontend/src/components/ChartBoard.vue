<template>
  <div class="chart-board-pro">
    <!-- 指标工具栏 -->
    <div class="indicator-toolbar">
      <span class="toolbar-label">指标:</span>
      <button
        v-for="ind in availableIndicators" :key="ind.name"
        class="ind-btn"
        :class="{ active: activeSet.has(ind.name) }"
        @click="toggleIndicator(ind)"
      >
        {{ ind.label }}
      </button>
    </div>
    <!-- KLineChart 容器 -->
    <div class="chart-container" ref="chartRef"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted, nextTick, computed } from 'vue'
import { init, dispose, registerOverlay } from 'klinecharts'

const props = defineProps<{
  data: any[]
  symbolName: string
  highlightedAnomalyIndex: number | null
}>()

const emit = defineEmits<{
  (e: 'anomaly-click', dataIndex: number): void
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: any = null
let tickIndex = 0
const markedAnomalyIndices = new Set<number>()  // 已标记的异动索引
let markDebounceTimer: ReturnType<typeof setTimeout> | null = null

// 指标配置
const availableIndicators = [
  { name: 'MA', label: 'MA', pane: 'candle_pane', overlay: true },
  { name: 'EMA', label: 'EMA', pane: 'candle_pane', overlay: true },
  { name: 'BOLL', label: 'BOLL', pane: 'candle_pane', overlay: true },
  { name: 'VOL', label: 'VOL', pane: 'vol_pane', overlay: false },
  { name: 'MACD', label: 'MACD', pane: 'macd_pane', overlay: false },
  { name: 'KDJ', label: 'KDJ', pane: 'kdj_pane', overlay: false },
  { name: 'RSI', label: 'RSI', pane: 'rsi_pane', overlay: false },
]

const activeSet = ref(new Set(['MA', 'VOL']))

// 收集异动点索引
const anomalyIndices = computed(() => {
  const indices: number[] = []
  props.data.forEach((item, i) => {
    if (item.hasAnomaly) indices.push(i)
  })
  return indices
})

// 使用一个不变的基准时间戳，确保每个 tick 递增 1s
const baseTs = new Date().setHours(9, 30, 0, 0)

function toKLine(item: any, idx: number) {
  return {
    timestamp: baseTs + idx * 60000,  // 每 tick 间隔 1 分钟（让 K 线分布更宽）
    open: Number(item.open) || 0,
    high: Number(item.high) || 0,
    low: Number(item.low) || 0,
    close: Number(item.close) || 0,
    volume: Number(item.volume) || 0,
  }
}

function initChart() {
  if (!chartRef.value) return
  if (chart) { try { dispose(chartRef.value) } catch(_){} }

  chart = init(chartRef.value, { locale: 'zh-CN' })
  if (!chart) { console.error('KLineChart init 失败'); return }

  // 用代码设置专业暗色样式
  chart.setStyles({
    grid: {
      show: true,
      horizontal: { show: true, size: 1, color: '#1e2530' },
      vertical: { show: true, size: 1, color: '#1e2530' },
    },
    candle: {
      type: 'candle_solid',
      bar: {
        upColor: '#26a69a',
        downColor: '#ef5350',
        noChangeColor: '#888',
        upBorderColor: '#26a69a',
        downBorderColor: '#ef5350',
        noChangeBorderColor: '#888',
        upWickColor: '#26a69a',
        downWickColor: '#ef5350',
        noChangeWickColor: '#888',
      },
      priceMark: {
        show: true,
        high: { show: true, color: '#ddd', textSize: 10 },
        low: { show: true, color: '#ddd', textSize: 10 },
        last: {
          show: true,
          upColor: '#26a69a',
          downColor: '#ef5350',
          noChangeColor: '#888',
          line: { show: true, size: 1 },
          text: { show: true, size: 11, paddingLeft: 4, paddingRight: 4, paddingTop: 3, paddingBottom: 3, color: '#fff' }
        }
      },
      tooltip: { showRule: 'always', showType: 'standard' }
    },
    indicator: {
      bars: [{
        upColor: 'rgba(38,166,154,0.65)',
        downColor: 'rgba(239,83,80,0.65)',
        noChangeColor: '#888',
      }],
      lines: [
        { size: 1, color: '#FF9600' },
        { size: 1, color: '#9D65C9' },
        { size: 1, color: '#2196F3' },
        { size: 1, color: '#E91E63' },
        { size: 1, color: '#00BCD4' },
      ],
    },
    xAxis: {
      axisLine: { color: '#2a3040' },
      tickLine: { color: '#2a3040' },
      tickText: { color: '#8b949e', size: 10 },
    },
    yAxis: {
      position: 'right',
      axisLine: { color: '#2a3040' },
      tickLine: { color: '#2a3040' },
      tickText: { color: '#8b949e', size: 10 },
    },
    separator: { size: 1, color: '#2a3040' },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, size: 1, color: '#4c525e' },
        text: { show: true, color: '#eee', size: 11, backgroundColor: '#373a40' }
      },
      vertical: {
        show: true,
        line: { show: true, size: 1, color: '#4c525e' },
        text: { show: true, color: '#eee', size: 11, backgroundColor: '#373a40' }
      }
    }
  })

  // 注册自定义异动标记 Overlay
  registerAnomalyOverlay()

  // 设置初始柱宽 — 让少量数据也能铺满图表
  chart.setBarSpace(40)
  chart.setOffsetRightDistance(80)

  // 加载初始数据
  loadAll()

  // 默认指标
  try {
    chart.createIndicator('MA', true, { id: 'candle_pane' })
    chart.createIndicator('VOL', false, { id: 'vol_pane' })
  } catch(e) { console.warn('默认指标异常:', e) }
}

// 注册异动标记覆盖物
function registerAnomalyOverlay() {
  if (!chart) return
  try {
    registerOverlay({
      name: 'anomalyMarker',
      totalStep: 0,
      needDefaultPointFigure: false,
      needDefaultXAxisFigure: false,
      needDefaultYAxisFigure: false,
      createPointFigures: ({ coordinates }: any) => {
        if (!coordinates?.length) return []
        const c = coordinates[0]
        return [{
          type: 'text',
          attrs: {
            x: c.x,
            y: c.y - 14,
            text: '▼',
            align: 'center',
            baseline: 'bottom',
          },
          styles: {
            color: '#ef5350',
            size: 14,
            family: 'sans-serif',
            weight: 'bold',
          }
        }]
      }
    })
  } catch(e) {
    // v9 兼容：如果 registerOverlay 不支持，静默忽略
    console.warn('Overlay 注册跳过:', e)
  }
}

// 增量式异动标记（只添加新的，不重建已有的）
function markAnomaliesIncremental() {
  if (!chart) return

  anomalyIndices.value.forEach((dataIdx) => {
    if (markedAnomalyIndices.has(dataIdx)) return  // 已标记过，跳过
    try {
      const ts = baseTs + dataIdx * 60000
      const item = props.data[dataIdx]
      const price = Number(item.high) || Number(item.close) || 0

      chart.createOverlay({
        name: 'anomalyMarker',
        points: [{ timestamp: ts, value: price }],
        lock: true,
        visible: true,
        onClick: () => {
          emit('anomaly-click', dataIdx)
          return true
        }
      })
      markedAnomalyIndices.add(dataIdx)
    } catch(e) {
      // 静默
    }
  })
}

// 防抖版本，避免高频触发
function markAnomaliesDebounced() {
  if (markDebounceTimer) clearTimeout(markDebounceTimer)
  markDebounceTimer = setTimeout(() => markAnomaliesIncremental(), 200)
}

function loadAll() {
  if (!chart || !props.data.length) return
  markedAnomalyIndices.clear()
  try { chart.removeOverlay() } catch(_) {}
  const kdata = props.data.map((d, i) => toKLine(d, i))
  tickIndex = props.data.length
  chart.applyNewData(kdata)
  nextTick(() => markAnomaliesIncremental())
}

function toggleIndicator(ind: typeof availableIndicators[0]) {
  if (!chart) return
  try {
    if (activeSet.value.has(ind.name)) {
      activeSet.value.delete(ind.name)
      activeSet.value = new Set(activeSet.value)
      chart.removeIndicator(ind.pane, ind.name)
    } else {
      activeSet.value.add(ind.name)
      activeSet.value = new Set(activeSet.value)
      chart.createIndicator(ind.name, ind.overlay, { id: ind.pane })
    }
  } catch(e) { console.warn('指标操作异常:', e) }
}

// 监听数据长度变化 — 增量推送
watch(() => props.data.length, (newLen, oldLen) => {
  if (!chart || newLen === 0) return
  try {
    if (!oldLen || newLen < oldLen) {
      loadAll()
    } else {
      for (let i = oldLen; i < newLen; i++) {
        const kd = toKLine(props.data[i], tickIndex++)
        chart.updateData(kd)
      }
      // 新数据中如果有异动，刷新标记
      const hasNewAnomaly = props.data.slice(oldLen).some(d => d.hasAnomaly)
      if (hasNewAnomaly) {
        markAnomaliesDebounced()
      }
    }
  } catch(e) { console.warn('图表数据更新异常:', e) }
})

// 切换标的时全量刷新
watch(() => props.symbolName, () => {
  tickIndex = 0
  nextTick(() => loadAll())
})

// 外部高亮某个异动点时，滚动到对应位置
watch(() => props.highlightedAnomalyIndex, (idx) => {
  if (idx === null || !chart) return
  try {
    const ts = baseTs + idx * 60000
    chart.scrollToTimestamp?.(ts)
  } catch(_) {}
})

let ro: ResizeObserver | null = null

onMounted(() => {
  nextTick(() => initChart())
  ro = new ResizeObserver(() => { try { chart?.resize() } catch(_){} })
  if (chartRef.value) ro.observe(chartRef.value)
})

onUnmounted(() => {
  ro?.disconnect()
  if (chartRef.value) { try { dispose(chartRef.value) } catch(_){} }
  chart = null
})
</script>

<style scoped>
.chart-board-pro {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #0d1117;
}

.indicator-toolbar {
  display: flex;
  align-items: center;
  padding: 4px 10px;
  gap: 4px;
  background-color: #161b22;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.toolbar-label {
  color: #8b949e;
  font-size: 11px;
  margin-right: 4px;
}

.ind-btn {
  background: #21262d;
  border: 1px solid #30363d;
  color: #8b949e;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.15s;
}

.ind-btn:hover {
  background: #30363d;
  color: #c9d1d9;
}

.ind-btn.active {
  background: rgba(38,166,154,0.15);
  border-color: #26a69a;
  color: #26a69a;
}

.chart-container {
  flex: 1;
  min-height: 0;
}
</style>
