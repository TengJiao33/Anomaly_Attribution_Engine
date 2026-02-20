<template>
  <div class="terminal-log">
    <div class="log-lines">
      <div v-for="(item, idx) in reversedData" :key="idx" class="log-entry">
        <div class="log-timestamp">
          <span class="bullet">▶</span> [{{ item.timestamp }}] <span class="blink-tag">检测到瞬时异动</span>
        </div>
        <div class="log-payload">
          <div class="log-summary"><span class="label">归因结论:</span> {{ item.anomalyDetails.summary }}</div>
          
          <div v-if="item.anomalyDetails && item.anomalyDetails.cot" class="log-cot-border">
             <div class="cot-meta">-- LLM 归因推理链路 (Chain of Thought) --</div>
             <div v-for="(step, sidx) in item.anomalyDetails.cot" :key="sidx" class="cot-step">
                {{ step }}
             </div>
          </div>

          <div v-if="item.anomalyDetails && item.anomalyDetails.links" class="log-kg-border">
            <div class="kg-meta">-- 核心关系图谱抽取 --</div>
            <div v-for="(link, lidx) in item.anomalyDetails.links" :key="lidx" class="kg-line">
               <span class="kw">[实体]</span> {{ link.source || '??' }} <span class="rel">--({{ link.value || '未知' }})--></span> <span class="kw">[实体]</span> {{ link.target || '??' }}
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
import { computed } from 'vue'

const props = defineProps<{
  data: any[] 
}>()

const reversedData = computed(() => {
  return [...props.data].reverse()
})
</script>

<style scoped>
.terminal-log {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--panel-bg);
  font-family: var(--font-mono); /* 保持这里的代码感 */
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
}

.log-timestamp {
  color: var(--down-color); /* 警报红 */
  font-weight: 600;
  margin-bottom: 6px;
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
  margin-left: 6px;
  font-family: var(--font-sans);
  animation: bg-blink 2s infinite; /* 减缓闪烁速度，保护眼睛 */
}

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

.log-cot-border {
  margin-top: 8px;
  margin-bottom: 8px;
  padding: 8px;
  background-color: rgba(63, 185, 80, 0.05); /* 淡淡的绿色背景代表逻辑推演 */
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
  color: #c9d1d9; /* GitHub dim text color */
  font-size: 12px;
  margin-bottom: 4px;
  line-height: 1.5;
  font-family: var(--font-mono);
}

.log-kg-border {
  color: var(--text-dim);
  background-color: rgba(255,255,255,0.02);
  padding: 8px;
  border-radius: 4px;
}

.kg-meta {
  color: #58a6ff;
  margin-bottom: 6px;
  font-size: 11px;
}

.kg-line {
  padding-left: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
  font-size: 12px;
}

.kw {
  color: #58a6ff; /* 使用护眼的高级蓝 */
  font-size: 11px;
}

.rel {
  color: var(--text-main);
  padding: 0 4px;
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
