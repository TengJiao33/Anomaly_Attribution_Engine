<template>
  <div class="terminal-log">
    <div class="log-lines" ref="logContainer">
      <div
        v-for="(item, idx) in reversedData"
        :key="item._uid || ('feed-' + idx)"
        class="log-entry"
        :class="{ 'highlighted': highlightedIndex !== null && getOriginalIndex(idx) === highlightedIndex }"
        :ref="(el) => setEntryRef(idx, el)"
        @click="handleCardClick(idx)"
      >
        <div class="log-timestamp">
          <span class="bullet">▶</span> [{{ item.timestamp }}] <span class="blink-tag">检测到瞬时异动</span>
          <span v-if="item.anomalyDetails?.attribution_source" class="source-badge" :class="item.anomalyDetails.attribution_source">
            {{ getSourceLabel(item.anomalyDetails.attribution_source) }}
          </span>
        </div>

        <!-- 多信号检测报告 -->
        <div v-if="item.detectionStats" class="detection-stats">
          <!-- 贝叶斯后验概率 -->
          <div class="stat-row bayesian-row">
            <span class="stat-label">异动后验概率:</span>
            <div class="prob-bar-container">
              <div class="prob-bar" :style="{ width: (item.detectionStats.anomaly_probability * 100) + '%' }"></div>
            </div>
            <span class="stat-value prob-value">{{ (item.detectionStats.anomaly_probability * 100).toFixed(1) }}%</span>
          </div>
          <!-- 子信号详情 -->
          <div class="signal-grid">
            <span class="stat-item" v-if="item.detectionStats.z_score !== undefined">
              Z-Score: <strong>{{ item.detectionStats.z_score }}σ</strong>
            </span>
            <span class="stat-item" v-if="item.detectionStats.volume_ratio !== undefined">
              量比: <strong>{{ item.detectionStats.volume_ratio }}x</strong>
            </span>
            <span class="stat-item" v-if="item.detectionStats.anomaly_score !== undefined">
              综合评分: <strong>{{ item.detectionStats.anomaly_score }}</strong>
            </span>
          </div>
          <!-- 各信号通道状态 -->
          <div v-if="item.detectionStats.signals" class="signals-detail">
            <div
              v-for="(sig, sname) in item.detectionStats.signals" :key="sname"
              class="signal-chip" :class="{ triggered: sig.triggered }"
            >
              <span class="sig-name">{{ getSignalLabel(sname) }}</span>
              <span class="sig-status">{{ sig.triggered ? '✓' : '—' }}</span>
            </div>
          </div>
          <span class="stat-item method">{{ item.detectionStats.detection_method }}</span>
        </div>

        <div class="log-payload">
          <div class="log-summary"><span class="label">归因结论:</span> {{ item.anomalyDetails.summary }}</div>

          <!-- 知识图谱可视化 -->
          <div v-if="item.anomalyDetails && item.anomalyDetails.nodes && item.anomalyDetails.nodes.length" class="kg-visual-section">
            <div class="section-meta">-- 瞬时异动知识图谱 (Force-Directed Graph) --</div>
            <KnowledgeGraph
              :nodes="item.anomalyDetails.nodes"
              :links="item.anomalyDetails.links || []"
            />
          </div>

          <div v-if="item.anomalyDetails && item.anomalyDetails.cot" class="log-cot-border">
             <div class="cot-meta">-- LLM 归因推理链路 (Chain of Thought) --</div>
             <div v-for="(step, sidx) in item.anomalyDetails.cot" :key="sidx" class="cot-step">
                {{ step }}
             </div>
          </div>
        </div>
      </div>
      <div v-if="!reversedData.length" class="log-idle">
        <span class="spinner">|</span> 系统监听中：等待盘面脉冲信号以触发联合归因分析...
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, watch } from 'vue'
import KnowledgeGraph from './KnowledgeGraph.vue'

const props = defineProps<{
  data: any[]
  highlightedIndex: number | null
}>()

const emit = defineEmits<{
  (e: 'card-click', dataIndex: number): void
}>()

const entryRefs = ref<Record<number, HTMLElement>>({})

const reversedData = computed(() => {
  return [...props.data].reverse()
})

// 将 reversed 索引转为原始 data 索引
const getOriginalIndex = (reversedIdx: number): number => {
  return props.data.length - 1 - reversedIdx
}

const setEntryRef = (idx: number, el: any) => {
  if (el) entryRefs.value[idx] = el as HTMLElement
}

const handleCardClick = (reversedIdx: number) => {
  const origIdx = getOriginalIndex(reversedIdx)
  emit('card-click', origIdx)
}

const getSourceLabel = (source: string): string => {
  const labels: Record<string, string> = {
    'live_llm': '🔴 Live LLM',
    'cached': '💾 Cached',
    'precomputed': '📦 Precomputed'
  }
  return labels[source] || source
}

const getSignalLabel = (name: any): string => {
  const labels: Record<string, string> = {
    'z_score': 'Z-Score',
    'cusum': 'CUSUM',
    'amihud': 'Amihud',
    'volume_surge': '量比',
  }
  return labels[name] || name
}

// 监听高亮索引变化，自动滚动到对应卡片
watch(() => props.highlightedIndex, (newIdx) => {
  if (newIdx === null) return
  const reversedIdx = props.data.length - 1 - newIdx
  nextTick(() => {
    const el = entryRefs.value[reversedIdx]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
})
</script>

<style scoped>
.terminal-log {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--panel-bg);
  font-family: var(--font-mono);
  font-size: 13px;
}

.log-lines {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.log-entry {
  margin-bottom: 16px;
  border-bottom: 1px dashed var(--border-color);
  padding-bottom: 16px;
  cursor: pointer;
  transition: background-color 0.3s, border-color 0.3s;
  border-radius: 6px;
  padding: 12px;
}

.log-entry:hover {
  background-color: rgba(88, 166, 255, 0.04);
}

.log-entry.highlighted {
  background-color: rgba(88, 166, 255, 0.1);
  border: 1px solid rgba(88, 166, 255, 0.3);
  box-shadow: 0 0 12px rgba(88, 166, 255, 0.1);
}

.log-timestamp {
  color: var(--down-color);
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.bullet {
  font-size: 10px;
  margin-right: 4px;
}

.blink-tag {
  background-color: var(--down-color);
  color: #fff;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: var(--font-sans);
  animation: bg-blink 2s infinite;
}

.source-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 10px;
  font-family: var(--font-sans);
  font-weight: 600;
}

.source-badge.live_llm {
  background-color: rgba(248, 81, 73, 0.2);
  color: var(--down-color);
  border: 1px solid rgba(248, 81, 73, 0.3);
}

.source-badge.cached {
  background-color: rgba(88, 166, 255, 0.15);
  color: #58a6ff;
  border: 1px solid rgba(88, 166, 255, 0.3);
}

.source-badge.precomputed {
  background-color: rgba(210, 168, 255, 0.15);
  color: var(--accent-color);
  border: 1px solid rgba(210, 168, 255, 0.3);
}

/* 多信号检测报告 */
.detection-stats {
  margin-bottom: 10px;
  padding: 8px 10px;
  background-color: rgba(248, 81, 73, 0.06);
  border-radius: 4px;
  border-left: 2px solid var(--down-color);
}

.bayesian-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

.prob-bar-container {
  flex: 1;
  height: 6px;
  background-color: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}

.prob-bar {
  height: 100%;
  background: linear-gradient(90deg, #ffa726, #ef5350);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.prob-value {
  font-size: 13px;
  font-weight: 700;
  color: var(--down-color);
  min-width: 48px;
  text-align: right;
}

.signal-grid {
  display: flex;
  gap: 12px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.stat-item {
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--font-mono);
}

.stat-item strong {
  color: var(--text-main);
}

.stat-item.method {
  color: var(--warning-color);
  font-weight: 500;
  display: block;
  margin-top: 4px;
}

.signals-detail {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.signal-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  background-color: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--text-dim);
}

.signal-chip.triggered {
  background-color: rgba(248, 81, 73, 0.15);
  border-color: rgba(248, 81, 73, 0.4);
  color: var(--down-color);
}

.sig-name { font-weight: 500; }
.sig-status { font-size: 11px; }

@keyframes bg-blink {
  40% { opacity: 1; }
  50% { opacity: 0.5; } 60% { opacity: 1; }
}

.log-payload {
  padding-left: 14px;
  border-left: 2px solid var(--border-color);
  margin-left: 5px;
}

.log-summary {
  color: var(--text-main);
  margin-bottom: 8px;
  line-height: 1.4;
  font-family: var(--font-sans);
}

.label {
  color: var(--text-dim);
  font-size: 12px;
}

/* 知识图谱可视化区域 */
.kg-visual-section {
  margin: 10px 0;
  padding: 8px;
  background-color: rgba(255,255,255,0.02);
  border-radius: 6px;
  border: 1px solid rgba(88, 166, 255, 0.1);
}

.section-meta {
  color: #58a6ff;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
}

.log-cot-border {
  margin-top: 8px;
  margin-bottom: 8px;
  padding: 8px;
  background-color: rgba(63, 185, 80, 0.05);
  border-left: 2px solid var(--up-color);
  border-radius: 0 4px 4px 0;
}

.cot-meta {
  color: var(--up-color);
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
}

.cot-step {
  color: #c9d1d9;
  font-size: 12px;
  margin-bottom: 4px;
  line-height: 1.5;
  font-family: var(--font-mono);
}

.log-idle {
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 8px;
}

.spinner {
  color: var(--up-color);
  display: inline-block;
  animation: spin 1s steps(4) infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
