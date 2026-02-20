import asyncio
import json
import os
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Optional, Dict

class AlignmentDataPoint(BaseModel):
    timestamp: str  
    open: float
    high: float
    low: float
    close: float
    volume: float
    hasAnomaly: bool
    anomalyDetails: Optional[Dict] = None
    
class AlignmentResponse(BaseModel):
    symbol: str
    symbolName: str
    data: List[AlignmentDataPoint]

class AlignmentEngineService:
    def __init__(self):
        self.data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'historical_slice.json')
        self.slice_data = self._load_slice()
        
    def _load_slice(self) -> dict:
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception as e:
            print(f"Error loading historical slice: {e}")
            return {"ticks": [], "precomputed_kg": {}}

    async def generate_historical_alignment(self, symbol: str) -> AlignmentResponse:
        """
        供前端首次加载时获取的前置上下文数据。
        为了回放的连续性，取切片的前三条数据作为初始状态。
        """
        symbol_name = self.slice_data.get("symbolName", "Unknown")
        ticks = self.slice_data.get("ticks", [])
        
        data_points = []
        # 以当前时间为基准，将历史切片的时间平移到现在
        now = datetime.now()
        
        if len(ticks) >= 3:
            initial_ticks = ticks[:3]
        else:
            initial_ticks = ticks

        for i, t in enumerate(initial_ticks):
            # 将切片时间映射到当前时间的几秒前（倒推）
            offset_seconds = (len(initial_ticks) - i) * 2
            ts_str = (now - timedelta(seconds=offset_seconds)).strftime("%H:%M:%S.000")
            
            p = t["price"]
            data_points.append(AlignmentDataPoint(
                timestamp=ts_str,
                open=p, high=p + 0.5, low=p - 0.5, close=p,
                volume=t["volume"],
                hasAnomaly=False
            ))
            
        return AlignmentResponse(symbol=self.slice_data.get("symbol", symbol), symbolName=symbol_name, data=data_points)

    async def stream_alignment_feed(self, symbol: str):
        """
        真实历史快照回放引擎：精准重放 Tick 和异动归因图谱
        """
        queue = asyncio.Queue()
        ticks = self.slice_data.get("ticks", [])
        if len(ticks) >= 3:
            replay_ticks = ticks[3:] # 跳过初始化的部分
        else:
            replay_ticks = []
            
        kg_data = self.slice_data.get("precomputed_kg", {})

        async def tick_producer():
            for t in replay_ticks:
                now = datetime.now()
                # 使用真实当前时间来驱动回放（让图表平缓移动）
                ts_str = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
                
                p = t["price"]
                vol = t["volume"]
                is_anomaly = t.get("isAnomaly", False)
                
                # 构造略带波动的 K线 (用单点价格模拟 OHLC)
                op = p - 0.5
                hi = p + (2.0 if is_anomaly else 0.5)
                lo = p - 1.0
                cl = p
                
                anomaly_details = None
                
                if is_anomaly:
                    anomaly_details = kg_data
                    print(f"[{ts_str}] 触发时序对齐！提取预计算知识图谱...")
                
                point_data = AlignmentDataPoint(
                    timestamp=ts_str,
                    open=round(op, 2),
                    high=round(hi, 2),
                    low=round(lo, 2),
                    close=round(cl, 2),
                    volume=round(vol, 0),
                    hasAnomaly=is_anomaly,
                    anomalyDetails=anomaly_details
                )
                
                await queue.put(point_data.model_dump())
                
                # 控制回放速度：每 1 秒推送下一帧 (模拟真实市场的高频跳动)
                await asyncio.sleep(1.0)
                
        producer_task = asyncio.create_task(tick_producer())
        
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            producer_task.cancel()

