<template>
  <div class="chart-board-raw" ref="chartContainerRef">
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted, shallowRef } from 'vue'
import { createChart, IChartApi, ISeriesApi, Time } from 'lightweight-charts'

const props = defineProps<{
  data: any[],
  symbolName: string
}>()

const chartContainerRef = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<"Candlestick"> | null = null
let volumeSeries: ISeriesApi<"Histogram"> | null = null

// 柔和的护眼终端配色
const upColor = '#3fb950' // 柔和绿
const downColor = '#f85149' // 柔和红
const termGrid = '#30363d' // 柔和边框
const termText = '#8b949e' // 柔和灰字
const panelBg = '#161b22'

// Parse custom timestamp format to unix timestamp or business day string
const parseTimestamp = (ts: string) => {
  if (!ts) return Math.floor(Date.now() / 1000) as Time;
  if (ts.includes('-')) {
    // "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DDTHH:MM:SSZ" or similar
    const dStr = ts.replace(' ', 'T');
    const dt = new Date(dStr);
    return isNaN(dt.getTime()) ? (Math.floor(Date.now() / 1000) as Time) : (Math.floor(dt.getTime() / 1000) as Time);
  } else {
    // "HH:MM:SS.mmm" - construct a fake today timestamp
    const today = new Date().toISOString().split('T')[0];
    const safeTime = ts.replace('.', '.000').substring(0, 12); // HH:MM:SS.mmm
    const dt = new Date(`${today}T${safeTime}Z`);
    if (isNaN(dt.getTime())) {
        return Math.floor(Date.now() / 1000) as Time;
    }
    return Math.floor(dt.getTime() / 1000) as Time;
  }
}

const renderChart = () => {
  if (!chart || !candleSeries || !volumeSeries || !props.data.length) return

  const cData: any[] = []
  const vData: any[] = []
  const markers: any[] = []
  let lastTime = 0
  
  for (let i = 0; i < props.data.length; i++) {
    const item = props.data[i]
    let timeRaw = parseTimestamp(item.timestamp)
    
    if (typeof timeRaw === 'number') {
      if (timeRaw <= lastTime) {
         timeRaw = (lastTime + 1) as Time;
      }
      lastTime = timeRaw;
    }

    cData.push({
      time: timeRaw,
      open: parseFloat(item.open),
      high: parseFloat(item.high),
      low: parseFloat(item.low),
      close: parseFloat(item.close)
    })

    vData.push({
      time: timeRaw,
      value: parseFloat(item.volume),
      color: parseFloat(item.close) > parseFloat(item.open) ? upColor : downColor
    })
    
    if (item.hasAnomaly) {
      markers.push({
        time: timeRaw,
        position: 'aboveBar',
        color: '#f85149',
        shape: 'arrowDown',
        text: '异动归因',
        size: 2
      })
    }
  }

  try {
    candleSeries.setData(cData)
    volumeSeries.setData(vData)
    if (markers.length > 0) {
      candleSeries.setMarkers(markers)
    }
    chart.timeScale().fitContent()
  } catch (err) {
    console.error("renderChart error:", err);
  }
}

watch(() => props.data, (newData, oldData) => {
    if (!chart || !candleSeries || !volumeSeries || !newData.length) return;
    
    if (oldData && newData.length > oldData.length) {
        const lastItems = newData.slice(oldData.length);
        let lastTime = 0;
        
        const currentData = candleSeries.data();
        if (currentData.length > 0) {
            const lastData = currentData[currentData.length - 1];
            if (lastData && typeof lastData.time === 'number') {
                lastTime = lastData.time;
            }
        }
        
        const markers: any[] = []; // Accumulate markers

        for (const item of lastItems) {
            let timeRaw = parseTimestamp(item.timestamp);
            if (typeof timeRaw === 'number') {
              if (timeRaw <= lastTime) {
                 timeRaw = (lastTime + 1) as Time;
              }
              lastTime = timeRaw;
            }

            try {
                candleSeries.update({
                    time: timeRaw,
                    open: parseFloat(item.open),
                    high: parseFloat(item.high),
                    low: parseFloat(item.low),
                    close: parseFloat(item.close)
                });
                volumeSeries.update({
                    time: timeRaw,
                    value: parseFloat(item.volume),
                    color: parseFloat(item.close) > parseFloat(item.open) ? upColor : downColor
                });
                
                if (item.hasAnomaly) {
                    markers.push({
                        time: timeRaw,
                        position: 'aboveBar',
                        color: '#f85149',
                        shape: 'arrowDown',
                        text: '异动归因',
                        size: 2
                    });
                }
            } catch(e) { /* ignore update error if data is out of order */ }
        }
        
        if (markers.length > 0) {
            // Append new markers to existing ones
            const currentMarkers = candleSeries.markers() || [];
            candleSeries.setMarkers([...currentMarkers, ...markers]);
        }
    } else {
        renderChart()
    }
}, { deep: true })

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  try {
      if (chartContainerRef.value) {
        chart = createChart(chartContainerRef.value, {
          layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: termText,
          },
          grid: {
            vertLines: { color: termGrid, style: 1 },
            horzLines: { color: termGrid, style: 1 },
          },
          crosshair: {
            mode: 1, 
            vertLine: { color: termText, labelBackgroundColor: panelBg },
            horzLine: { color: termText, labelBackgroundColor: panelBg }
          },
          rightPriceScale: { borderColor: termGrid },
          timeScale: { borderColor: termGrid, timeVisible: true, secondsVisible: true },
          watermark: {
            color: 'rgba(255, 255, 255, 0.05)',
            visible: true,
            text: props.symbolName || '异动雷达',
            fontSize: 48,
            horzAlign: 'center',
            vertAlign: 'center',
          }
        });

        candleSeries = chart.addCandlestickSeries({
          upColor: upColor, downColor: downColor,
          borderDownColor: downColor, borderUpColor: upColor,
          wickDownColor: downColor, wickUpColor: upColor,
        });

        volumeSeries = chart.addHistogramSeries({
          color: upColor,
          priceFormat: { type: 'volume' },
          priceScaleId: '', 
        });

        // Safe way to apply price scale margins
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        renderChart()
      }
      
      resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || entries[0].target !== chartContainerRef.value) { return; }
        const newRect = entries[0].contentRect;
        if (chart && newRect.height > 0 && newRect.width > 0) {
            chart.applyOptions({ height: newRect.height, width: newRect.width });
        }
      });

      if (chartContainerRef.value) {
        resizeObserver.observe(chartContainerRef.value);
      }

      window.addEventListener('resize', handleResize)
  } catch (err) {
      console.error("ChartBoard mount error:", err);
  }
})

const handleResize = () => {
    if (chartContainerRef.value && chart) {
        if (chartContainerRef.value.clientWidth > 0 && chartContainerRef.value.clientHeight > 0) {
            chart.applyOptions({
                width: chartContainerRef.value.clientWidth,
                height: chartContainerRef.value.clientHeight
            })
        }
    }
}

onUnmounted(() => { 
    window.removeEventListener('resize', handleResize); 
    if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
    }
    if (chart) {
        chart.remove();
        chart = null;
    }
})
</script>

<style scoped>
.chart-board-raw {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  position: absolute; /* Ensures it fills panel-body */
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}
</style>
