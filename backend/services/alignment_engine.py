"""
时序对齐引擎 (Alignment Engine Service)

核心服务：重构版。真正集成：
1. SQLite 时序存储（替代静态 JSON）
2. AnomalyDetector 统计学异动检测（替代硬编码标记）
3. AttributionAnalyzer 大模型归因（真正调用 LLM）
4. RedisCache 缓存层（LLM 结果缓存 + 系统指标）
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from loguru import logger

from services.timeseries_db import TimeSeriesDB
from services.multi_signal_detector import MultiSignalDetector
from services.redis_cache import RedisCache
from ai_engine.attribution_analyzer import AttributionAnalyzer


class AlignmentDataPoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    hasAnomaly: bool
    anomalyDetails: Optional[Dict] = None
    detectionStats: Optional[Dict] = None  # 新增：检测统计信息


class AlignmentResponse(BaseModel):
    symbol: str
    symbolName: str
    data: List[AlignmentDataPoint]


class CaseInfo(BaseModel):
    case_id: str
    symbol: str
    symbol_name: str
    case_date: str
    description: str
    anomaly_type: str
    tick_count: int = 0
    news_count: int = 0


class AlignmentEngineService:
    """时序对齐引擎 — 核心服务"""

    def __init__(self):
        self.cases_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cases')
        self.cases_index = self._load_cases_index()
        self.analyzer = AttributionAnalyzer()
        self.cache = RedisCache(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379))
        )
        # 系统事件日志（供前端 TickerTape 消费）
        self.system_events: List[Dict] = []
        self._add_event("system", "时序对齐引擎初始化完成")
        self._add_event("system", f"已加载 {len(self.cases_index)} 个历史案例")
        
        logger.info(f"AlignmentEngine 初始化完成，{len(self.cases_index)} 个案例就绪")

    def _load_cases_index(self) -> List[Dict]:
        """加载案例索引"""
        index_path = os.path.join(self.cases_dir, "cases_index.json")
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("案例索引文件不存在，请先运行 scripts/prepare_case.py")
            return []

    def _get_case_by_symbol(self, symbol: str) -> Optional[Dict]:
        """根据标的代码查找案例（取第一个匹配）"""
        for case in self.cases_index:
            if case["symbol"] == symbol:
                return case
        return None

    def _get_case_by_id(self, case_id: str) -> Optional[Dict]:
        """根据案例 ID 查找"""
        for case in self.cases_index:
            if case["case_id"] == case_id:
                return case
        return None

    def _open_case_db(self, case_id: str) -> TimeSeriesDB:
        """打开指定案例的 SQLite 数据库"""
        db_path = os.path.join(self.cases_dir, case_id, "timeseries.db")
        return TimeSeriesDB(db_path)

    def _load_precomputed_kg(self, case_id: str) -> Optional[Dict]:
        """加载预计算的知识图谱（LLM fallback）"""
        kg_path = os.path.join(self.cases_dir, case_id, "precomputed_kg.json")
        try:
            with open(kg_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _add_event(self, event_type: str, message: str):
        """添加系统事件"""
        event = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": event_type,
            "message": message
        }
        self.system_events.append(event)
        # 保留最近 50 条
        if len(self.system_events) > 50:
            self.system_events = self.system_events[-50:]

    # ===== 公开 API ===== #

    def get_available_cases(self) -> List[CaseInfo]:
        """获取所有可用案例列表"""
        return [CaseInfo(**case) for case in self.cases_index]

    def get_system_events(self) -> List[Dict]:
        """获取系统事件日志"""
        return self.system_events[-20:]

    def get_system_metrics(self) -> Dict:
        """获取系统运行指标"""
        return self.cache.get_system_metrics()

    async def generate_historical_alignment(
        self, case_id: str
    ) -> AlignmentResponse:
        """
        获取指定案例的初始上下文数据（前端首次加载）。
        取切片数据的前 N 条作为初始快照。
        """
        case = self._get_case_by_id(case_id)
        if not case:
            # 尝试按 symbol 查找（兼容旧接口）
            case = self._get_case_by_symbol(case_id)
        
        if not case:
            logger.warning(f"案例不存在: {case_id}")
            return AlignmentResponse(symbol=case_id, symbolName="Unknown", data=[])

        db = self._open_case_db(case["case_id"])
        ticks = db.get_ticks(case["symbol"], limit=500)
        db.close()

        if not ticks:
            return AlignmentResponse(
                symbol=case["symbol"],
                symbolName=case["symbol_name"],
                data=[]
            )

        # 只返回前3条作为初始上下文（后续通过 WebSocket 逐条推送）
        initial_ticks = ticks[:3]
        now = datetime.now()

        data_points = []
        for i, t in enumerate(initial_ticks):
            offset_seconds = (len(initial_ticks) - i) * 2
            ts_str = (now - timedelta(seconds=offset_seconds)).strftime("%H:%M:%S.000")
            
            data_points.append(AlignmentDataPoint(
                timestamp=ts_str,
                open=t["open"], high=t["high"],
                low=t["low"], close=t["close"],
                volume=t["volume"],
                hasAnomaly=False
            ))

        self._add_event("replay", f"加载案例 [{case['symbol_name']}] 初始快照")

        return AlignmentResponse(
            symbol=case["symbol"],
            symbolName=case["symbol_name"],
            data=data_points
        )

    async def stream_alignment_feed(self, case_id: str, control_state: dict = None):
        """
        核心：历史切片回放引擎 + 实时异动检测 + LLM 归因
        
        数据流：
        SQLite Ticks → MultiSignalDetector → [异动触发] → 时间窗口查询资讯 → LLM 归因
        
        :param control_state: 回放控制状态 {paused: bool, speed: float}，由 WebSocket 端动态更新
        """
        if control_state is None:
            control_state = {"paused": False, "speed": 1.0}
        case = self._get_case_by_id(case_id)
        if not case:
            case = self._get_case_by_symbol(case_id)
        if not case:
            logger.error(f"流式回放失败：案例不存在 {case_id}")
            return

        db = self._open_case_db(case["case_id"])
        ticks = db.get_ticks(case["symbol"], limit=500)

        if len(ticks) <= 3:
            db.close()
            return

        # 跳过初始化推送的前3条（仅用于检测器预热，但也推送给前端显示K线）
        warmup_ticks = ticks[:3]
        replay_ticks = ticks[3:]
        
        # 初始化异动检测器（使用前3条做预热）
        detector = MultiSignalDetector(
            window_size=5, z_threshold=1.5, volume_surge=2.0,
            cusum_drift=0.003, cusum_h=0.01,
            amihud_surge=2.0, posterior_threshold=0.35
        )
        for t in ticks[:3]:
            detector.feed(t["price"], t["volume"])

        # 加载预计算知识图谱作为 fallback
        precomputed_kg = self._load_precomputed_kg(case["case_id"])

        self._add_event("replay", f"开始回放 [{case['symbol_name']}]，共 {len(ticks)} 个 Tick")
        self.cache.increment_metric("ws_connections")

        queue = asyncio.Queue()

        async def tick_producer():
            # 先推送预热数据（非异动，用于前端绘制完整K线）
            for t in warmup_ticks:
                now = datetime.now()
                ts_str = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
                point_data = AlignmentDataPoint(
                    timestamp=ts_str,
                    open=round(t["open"], 2),
                    high=round(t["high"], 2),
                    low=round(t["low"], 2),
                    close=round(t["close"], 2),
                    volume=round(t["volume"], 0),
                    hasAnomaly=False,
                    anomalyDetails=None,
                    detectionStats=None
                )
                await queue.put(point_data.model_dump())
                self.cache.increment_metric("total_ticks_pushed")
                await asyncio.sleep(0.15)  # 快速推送预热数据

            # 再推送检测数据
            for t in replay_ticks:
                now = datetime.now()
                ts_str = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"

                # ---- 异动检测（真正的算法） ---- #
                detection = detector.feed(t["price"], t["volume"])
                is_anomaly = detection["is_anomaly"]

                anomaly_details = None
                if is_anomaly:
                    self.cache.increment_metric("anomalies_detected")
                    prob = detection.get('anomaly_probability', 0)
                    self._add_event("anomaly",
                        f"检测到 {case['symbol']} 异动! "
                        f"P(anomaly)={prob:.1%}, Z={detection['z_score']:.2f}σ, "
                        f"量比={detection['volume_ratio']:.1f}x"
                    )
                    logger.info(
                        f"[{ts_str}] 🚨 异动触发 | {case['symbol']} | "
                        f"P={prob:.1%} | Z={detection['z_score']:.2f}σ | "
                        f"Vol={detection['volume_ratio']:.1f}x"
                    )

                    # ---- 时间窗口对齐：查询异动前后的资讯 ---- #
                    aligned_news = db.get_aligned_news(
                        case["symbol"], t["timestamp"],
                        window_before_sec=120, window_after_sec=30
                    )
                    
                    if aligned_news:
                        news_text = "\n".join([
                            f"[{n['timestamp']}][{n['source']}] {n['content']}"
                            for n in aligned_news
                        ])
                        self._add_event("alignment",
                            f"时序对齐完成：{t['timestamp']} 前后窗口命中 {len(aligned_news)} 条资讯"
                        )
                    else:
                        news_text = ""

                    # ---- LLM 归因（带缓存 + fallback） ---- #
                    attribution_source = "precomputed"
                    
                    if news_text:
                        # 先查缓存
                        cached = self.cache.get_cached_kg(news_text)
                        if cached:
                            anomaly_details = cached
                            attribution_source = "cached"
                            self._add_event("llm", "命中归因缓存 [Cache Hit]")
                        else:
                            # 尝试实时调用 LLM
                            try:
                                llm_start = time.time()
                                kg_result = await self.analyzer.extract_knowledge_graph(news_text)
                                llm_latency = (time.time() - llm_start) * 1000
                                
                                self.cache.increment_metric("llm_calls")
                                self.cache.set_metric("avg_llm_latency_ms", round(llm_latency))
                                
                                if kg_result and "summary" in kg_result:
                                    anomaly_details = kg_result
                                    self.cache.set_cached_kg(news_text, kg_result)
                                    attribution_source = "live_llm"
                                    self._add_event("llm",
                                        f"LLM 实时归因完成，延迟 {llm_latency:.0f}ms"
                                    )
                            except Exception as e:
                                logger.warning(f"LLM 调用失败，使用预计算 fallback: {e}")
                                self._add_event("llm", f"LLM 调用异常，降级为预计算: {str(e)[:50]}")

                    # Fallback: 使用预计算的知识图谱
                    if anomaly_details is None and precomputed_kg:
                        anomaly_details = precomputed_kg
                        attribution_source = "precomputed"
                        self._add_event("llm", "使用预计算知识图谱 [Precomputed Fallback]")

                    # 注入归因来源标识
                    if anomaly_details:
                        anomaly_details = {
                            **anomaly_details,
                            "attribution_source": attribution_source
                        }

                point_data = AlignmentDataPoint(
                    timestamp=ts_str,
                    open=round(t["open"], 2),
                    high=round(t["high"], 2),
                    low=round(t["low"], 2),
                    close=round(t["close"], 2),
                    volume=round(t["volume"], 0),
                    hasAnomaly=is_anomaly,
                    anomalyDetails=anomaly_details,
                    detectionStats=detection if is_anomaly else None
                )

                await queue.put(point_data.model_dump())
                self.cache.increment_metric("total_ticks_pushed")

                # 回放控制：暂停等待
                while control_state.get("paused", False):
                    await asyncio.sleep(0.1)

                # 回放控制：动态速度
                speed = max(control_state.get("speed", 1.0), 0.1)
                await asyncio.sleep(1.0 / speed)

        producer_task = asyncio.create_task(tick_producer())

        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            producer_task.cancel()
            db.close()
            self.cache.increment_metric("ws_connections", -1)
