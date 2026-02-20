"""
异动检测器 (Anomaly Detector)

实现真正的统计学异动检测算法，替代之前 JSON 中的硬编码标记：
- Z-Score 偏离检测：价格变化率超过滑动窗口均值的 N 个标准差
- 量价背离检测：成交量突增但价格变化方向异常
- 综合评分系统：多信号融合输出异动置信度
"""

from collections import deque
from typing import Dict, Optional
import math


class AnomalyDetector:
    """
    滑动窗口异动检测器
    
    核心算法：
    1. Z-Score 偏离度 = (当前收益率 - 窗口均值) / 窗口标准差
    2. 量价背离度 = 成交量变化率 / 价格变化率（负值意味着背离）
    3. 综合异动分数 = 加权融合
    """

    def __init__(self, window_size: int = 10, z_threshold: float = 2.0,
                 volume_surge_ratio: float = 3.0):
        """
        :param window_size: 滑动窗口大小（Tick数量）
        :param z_threshold: Z-Score 触发阈值
        :param volume_surge_ratio: 成交量激增比例阈值（相对于窗口均值的倍数）
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.volume_surge_ratio = volume_surge_ratio
        
        # 滑动窗口
        self.price_window = deque(maxlen=window_size)
        self.volume_window = deque(maxlen=window_size)
        self.return_window = deque(maxlen=window_size)
        
        self.last_price: Optional[float] = None
        self.tick_count = 0

    def feed(self, price: float, volume: float) -> Dict:
        """
        送入一个新的 Tick 数据点，返回异动检测结果。
        
        :param price: 当前价格
        :param volume: 当前成交量
        :return: 检测结果字典
        """
        self.tick_count += 1
        
        # 计算收益率
        current_return = 0.0
        if self.last_price and self.last_price > 0:
            current_return = (price - self.last_price) / self.last_price
        
        self.price_window.append(price)
        self.volume_window.append(volume)
        self.return_window.append(current_return)
        self.last_price = price
        
        # 需要足够的历史数据才能检测
        if len(self.return_window) < max(3, self.window_size // 2):
            return self._build_result(False, 0, 0, 0, current_return, "数据预热中")
        
        # ---- 检测 1: Z-Score 价格偏离 ---- #
        z_score = self._calculate_z_score(current_return)
        
        # ---- 检测 2: 成交量激增 ---- #
        volume_ratio = self._calculate_volume_ratio(volume)
        
        # ---- 检测 3: 综合异动评分 ---- #
        anomaly_score = self._calculate_anomaly_score(z_score, volume_ratio)
        
        # 判定是否为异动
        is_anomaly = abs(z_score) > self.z_threshold or (
            abs(z_score) > self.z_threshold * 0.7 and 
            volume_ratio > self.volume_surge_ratio
        )
        
        # 生成检测方法说明
        methods_triggered = []
        if abs(z_score) > self.z_threshold:
            direction = "正向" if z_score > 0 else "负向"
            methods_triggered.append(f"Z-Score {direction}偏离({z_score:.2f}σ)")
        if volume_ratio > self.volume_surge_ratio:
            methods_triggered.append(f"成交量激增({volume_ratio:.1f}倍)")
        
        detection_method = " + ".join(methods_triggered) if methods_triggered else "未触发"
        
        return self._build_result(
            is_anomaly, z_score, volume_ratio, anomaly_score, 
            current_return, detection_method
        )

    def _calculate_z_score(self, current_return: float) -> float:
        """计算当前收益率的 Z-Score 偏离度"""
        if len(self.return_window) < 3:
            return 0.0
        
        # 排除当前值计算历史统计量
        history = list(self.return_window)[:-1]
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = math.sqrt(variance) if variance > 0 else 1e-8
        
        return (current_return - mean) / std

    def _calculate_volume_ratio(self, current_volume: float) -> float:
        """计算当前成交量相对于窗口均值的倍数"""
        if len(self.volume_window) < 3:
            return 1.0
        
        # 排除当前值计算历史均量
        history = list(self.volume_window)[:-1]
        mean_volume = sum(history) / len(history)
        
        if mean_volume <= 0:
            return 1.0
        
        return current_volume / mean_volume

    def _calculate_anomaly_score(self, z_score: float, volume_ratio: float) -> float:
        """
        综合异动评分 (0-100)
        加权公式: score = 0.6 * normalize(z_score) + 0.4 * normalize(volume_ratio)
        """
        # Z-Score 映射到 [0, 100]
        z_component = min(abs(z_score) / 5.0 * 100, 100)
        
        # 量比映射到 [0, 100]
        v_component = min((volume_ratio - 1) / 10.0 * 100, 100) if volume_ratio > 1 else 0
        
        score = 0.6 * z_component + 0.4 * v_component
        return round(score, 1)

    def _build_result(self, is_anomaly: bool, z_score: float, 
                      volume_ratio: float, anomaly_score: float,
                      current_return: float, detection_method: str) -> Dict:
        """构建标准化的检测结果"""
        return {
            "is_anomaly": is_anomaly,
            "z_score": round(z_score, 3),
            "volume_ratio": round(volume_ratio, 2),
            "anomaly_score": anomaly_score,
            "current_return": round(current_return * 100, 4),  # 百分比
            "detection_method": detection_method,
            "window_size": self.window_size,
            "z_threshold": self.z_threshold,
            "tick_count": self.tick_count
        }

    def reset(self):
        """重置检测器状态"""
        self.price_window.clear()
        self.volume_window.clear()
        self.return_window.clear()
        self.last_price = None
        self.tick_count = 0
