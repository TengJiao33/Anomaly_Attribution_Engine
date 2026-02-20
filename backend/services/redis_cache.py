"""
Redis 缓存服务层 (Redis Cache Service)

提供：
- LLM 归因结果缓存（避免重复调用）
- 系统运行状态指标发布
- 优雅降级（Redis 不可用时使用内存缓存）
"""

import json
import hashlib
import time
from typing import Dict, Optional


class RedisCache:
    """
    Redis 缓存层，支持优雅降级到内存字典。
    当 Redis 不可用时，自动使用本地内存缓存。
    """

    def __init__(self, host: str = "localhost", port: int = 6379):
        self.redis_client = None
        self._memory_cache: Dict[str, str] = {}
        self._system_metrics: Dict[str, any] = {
            "ws_connections": 0,
            "total_ticks_pushed": 0,
            "anomalies_detected": 0,
            "llm_calls": 0,
            "llm_cache_hits": 0,
            "avg_llm_latency_ms": 0,
            "uptime_start": time.time()
        }

        try:
            import redis
            self.redis_client = redis.Redis(host=host, port=port, db=0,
                                            decode_responses=True,
                                            socket_timeout=2)
            self.redis_client.ping()
            self._use_redis = True
            print(f"[RedisCache] 已连接 Redis @ {host}:{port}")
        except Exception as e:
            self._use_redis = False
            print(f"[RedisCache] Redis 不可用（{e}），降级为内存缓存")

    def _make_key(self, text: str) -> str:
        """根据文本内容生成缓存键"""
        return f"llm_kg:{hashlib.md5(text.encode()).hexdigest()}"

    def get_cached_kg(self, text: str) -> Optional[Dict]:
        """查询 LLM 归因缓存"""
        key = self._make_key(text)
        try:
            if self._use_redis:
                raw = self.redis_client.get(key)
            else:
                raw = self._memory_cache.get(key)

            if raw:
                self._system_metrics["llm_cache_hits"] += 1
                return json.loads(raw)
        except Exception:
            pass
        return None

    def set_cached_kg(self, text: str, kg_data: Dict, ttl: int = 3600):
        """写入 LLM 归因缓存"""
        key = self._make_key(text)
        try:
            value = json.dumps(kg_data, ensure_ascii=False)
            if self._use_redis:
                self.redis_client.setex(key, ttl, value)
            else:
                self._memory_cache[key] = value
        except Exception:
            pass

    def increment_metric(self, metric_name: str, amount: int = 1):
        """增加系统指标计数"""
        if metric_name in self._system_metrics:
            self._system_metrics[metric_name] += amount

    def set_metric(self, metric_name: str, value):
        """设置系统指标值"""
        self._system_metrics[metric_name] = value

    def get_system_metrics(self) -> Dict:
        """获取所有系统运行指标"""
        uptime = time.time() - self._system_metrics["uptime_start"]
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        return {
            **self._system_metrics,
            "uptime_formatted": f"{hours}h {minutes}m",
            "cache_mode": "Redis" if self._use_redis else "Memory",
            "cache_entries": self._get_cache_size()
        }

    def _get_cache_size(self) -> int:
        """获取缓存条目数量"""
        try:
            if self._use_redis:
                return self.redis_client.dbsize()
            return len(self._memory_cache)
        except Exception:
            return 0
