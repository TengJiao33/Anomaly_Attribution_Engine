<template>
  <div class="kg-wrapper">
    <!-- 将 3D 图表挂载到这个 div -->
    <div class="kg-container" ref="chartRef"></div>
    
    <!-- 自定义的浮动提示框 (Tooltip) -->
    <div v-if="hoverTooltip" class="kg-tooltip" :style="{ top: hoverTooltip.y + 'px', left: hoverTooltip.x + 'px' }">
      <div class="tt-header">
        <span class="tt-color" :style="{ backgroundColor: hoverTooltip.color }"></span>
        {{ hoverTooltip.type }}
      </div>
      <div class="tt-body">{{ hoverTooltip.name }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import ForceGraph3D from '3d-force-graph'

const props = defineProps<{
  nodes: Array<{ id: string; group: string }>
  links: Array<{ source: string; target: string; value: string }>
}>()

const chartRef = ref<HTMLElement | null>(null)
let graphInstance: any = null

// 实体类型 → 颜色映射（金融专业配色，适配 3D 黑夜模式）
const groupColors: Record<string, string> = {
  stock: '#ef5350',     // 红 — 股票标的
  company: '#ef5350',
  concept: '#42a5f5',   // 蓝 — 概念板块
  sector: '#42a5f5',
  source: '#66bb6a',    // 绿 — 信息来源
  capital: '#ffa726',   // 金 — 资金流向
  action: '#ab47bc',    // 紫 — 操作动作
  policy: '#ec407a',    // 玫红 — 政策
  background: '#78909c',// 灰蓝 — 背景信息
  pattern: '#26c6da',   // 青 — 行为模式
  error: '#ff7043',     // 橙红 — 异常
}

// 节点大小映射
const groupSizes: Record<string, number> = {
  stock: 8,
  company: 8,
  concept: 6,
  sector: 6,
  source: 4,
  capital: 5,
  action: 4,
  policy: 7,
  background: 3,
  pattern: 4,
  error: 6,
}

const hoverTooltip = ref<{ x: number, y: number, name: string, type: string, color: string } | null>(null)

function renderGraph() {
  if (!chartRef.value || !props.nodes?.length) return

  // 格式化数据给 3d-force-graph
  const graphData = {
    nodes: props.nodes.map(n => ({
      id: n.id,
      name: n.id,
      group: n.group,
      color: groupColors[n.group] || '#78909c',
      val: groupSizes[n.group] || 5
    })),
    links: props.links.map(l => ({
      source: l.source,
      target: l.target,
      name: l.value
    }))
  }

  // 销毁旧实例
  if (graphInstance) {
    graphInstance._destructor()
  }

  // 初始化 3D 力导向图
  // @ts-ignore: ForceGraph3D allows function execution without new
  graphInstance = ForceGraph3D()(chartRef.value as HTMLElement)
    .graphData(graphData)
    .width((chartRef.value as HTMLElement).clientWidth)
    .height(200) // 与之前的 min-height 保持一致
    .backgroundColor('#0d1117') // 深色星空背景
    .nodeAutoColorBy('group')
    .nodeColor((node: any) => node.color)
    .nodeRelSize(4)
    .nodeResolution(32) // 球体圆滑度
    .linkColor(() => 'rgba(88, 166, 255, 0.4)')
    .linkWidth(0.8)
    .linkDirectionalArrowLength(3.5)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(2) // 开启链路粒子流动特效
    .linkDirectionalParticleWidth(1.2)
    .linkDirectionalParticleSpeed(0.005)
    
    // 禁用自带的 HTML tooltip，我们使用 Vue 接管
    .onNodeHover((node: any) => {
      // 鼠标光标变化
      chartRef.value!.style.cursor = node ? 'pointer' : 'default';
      
      if (node) {
        // 让选中的节点高亮（通过临时调整粒子、连线）
        hoverTooltip.value = {
           name: node.name,
           type: node.group.toUpperCase(),
           color: node.color,
           x: 0, // 将在 mousemove 中更新
           y: 0
        }
      } else {
        hoverTooltip.value = null
      }
    })
    .onLinkHover((link: any) => {
       chartRef.value!.style.cursor = link ? 'pointer' : 'default';
       if (link) {
           hoverTooltip.value = {
               name: link.name || '相连',
               type: 'RELATION',
               color: '#58a6ff',
               x: 0,
               y: 0
           }
       } else {
           hoverTooltip.value = null
       }
    })

  // 镜头自动适配
  graphInstance.cameraPosition({ z: 120 });
}

// 监听鼠标移动以更新 tooltip 位置
const handleMouseMove = (e: MouseEvent) => {
    if (hoverTooltip.value) {
        // 利用 offset 计算相对于容器的位置，加上微小偏移避免遮挡鼠标
        const rect = chartRef.value?.getBoundingClientRect()
        if (rect) {
            hoverTooltip.value.x = e.clientX - rect.left + 15
            hoverTooltip.value.y = e.clientY - rect.top + 15
        }
    }
}

onMounted(() => {
  nextTick(() => {
      renderGraph()
      chartRef.value?.addEventListener('mousemove', handleMouseMove)
  })
})

onUnmounted(() => {
  if (graphInstance) {
    graphInstance._destructor()
  }
  chartRef.value?.removeEventListener('mousemove', handleMouseMove)
})
</script>

<style scoped>
.kg-wrapper {
  position: relative;
  width: 100%;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(88, 166, 255, 0.1);
}

.kg-container {
  width: 100%;
  height: 200px;
  min-height: 200px;
  background-color: #0d1117;
  cursor: grab;
}

.kg-container:active {
  cursor: grabbing;
}

/* 自定义浮动提示框 */
.kg-tooltip {
  position: absolute;
  background-color: rgba(13, 17, 23, 0.9);
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 8px 12px;
  pointer-events: none; /* 让鼠标穿透，防止闪烁 */
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  min-width: 120px;
  transition: opacity 0.1s;
}

.tt-header {
  font-size: 10px;
  color: #8b949e;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  font-family: var(--font-mono);
}

.tt-color {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.tt-body {
  font-size: 13px;
  color: #e6edf3;
  font-weight: 500;
}
</style>
