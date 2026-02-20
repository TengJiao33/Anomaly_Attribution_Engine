"""
多维信号融合异动检测器 (Multi-Signal Anomaly Detector)

学术级异动检测框架，融合多个独立信号通道：
1. Z-Score 价格偏离检测（保留原有基线）
2. CUSUM 变点检测 (Page, 1954) — 累积和控制图
3. Amihud 非流动性因子 (Amihud, 2002) — 市场微观结构信号
4. 成交量激增比率

通过贝叶斯后验更新将多信号融合为统一异动概率 P(anomaly|signals)。
"""

from collections import deque
from typing import Dict, List, Optional
import math


class SignalChannel:
    """单个信号通道的基类"""

    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight

    def compute(self, price: float, volume: float, ret: float, history: dict) -> Dict:
        """计算该信号的置信度，返回 {value, confidence, triggered, desc}"""
        raise NotImplementedError


class ZScoreSignal(SignalChannel):
    """Z-Score 价格偏离信号"""

    def __init__(self, threshold: float = 2.0):
        super().__init__("z_score", weight=0.3)
        self.threshold = threshold

    def compute(self, price, volume, ret, history) -> Dict:
        returns = history.get("returns", [])
        if len(returns) < 3:
            return {"value": 0, "confidence": 0, "triggered": False, "desc": "数据预热中"}

        mean = sum(returns) / len(returns)
        variance = sum((x - mean) ** 2 for x in returns) / len(returns)
        std = math.sqrt(variance) if variance > 0 else 1e-8
        z = (ret - mean) / std

        # 将 |z| 映射到 [0, 1] 的置信度
        confidence = min(abs(z) / (self.threshold * 2.5), 1.0)
        triggered = abs(z) > self.threshold
        direction = "正向" if z > 0 else "负向"

        return {
            "value": round(z, 3),
            "confidence": round(confidence, 4),
            "triggered": triggered,
            "desc": f"Z-Score {direction}偏离 {z:.2f}σ" if triggered else f"Z={z:.2f}σ (阈值{self.threshold}σ)"
        }


class CUSUMSignal(SignalChannel):
    """
    CUSUM 变点检测信号 (Cumulative Sum Control Chart)

    参考: Page, E.S. (1954). "Continuous Inspection Schemes"
    算法: 维护正/负两个累积偏差统计量 S+ 和 S-，当任一超过阈值 h 时认定均值发生漂移。
    """

    def __init__(self, drift: float = 0.005, threshold_h: float = 0.02):
        """
        :param drift: 允许的正常漂移量 k（容差系数）
        :param threshold_h: 触发阈值 h
        """
        super().__init__("cusum", weight=0.3)
        self.drift = drift
        self.threshold_h = threshold_h
        self.s_pos = 0.0  # 正向累积偏差
        self.s_neg = 0.0  # 负向累积偏差

    def compute(self, price, volume, ret, history) -> Dict:
        returns = history.get("returns", [])
        if len(returns) < 3:
            return {"value": 0, "confidence": 0, "triggered": False, "desc": "CUSUM 预热中"}

        mean = sum(returns) / len(returns)

        # 更新 CUSUM 统计量
        self.s_pos = max(0, self.s_pos + (ret - mean) - self.drift)
        self.s_neg = max(0, self.s_neg - (ret - mean) - self.drift)

        cusum_val = max(self.s_pos, self.s_neg)
        triggered = cusum_val > self.threshold_h
        confidence = min(cusum_val / (self.threshold_h * 2), 1.0)

        if triggered:
            direction = "上行突变" if self.s_pos > self.s_neg else "下行突变"
            desc = f"CUSUM {direction} (S={cusum_val:.4f}, h={self.threshold_h})"
            # 触发后重置（避免持续报警）
            self.s_pos = 0.0
            self.s_neg = 0.0
        else:
            desc = f"CUSUM S+={self.s_pos:.4f}, S-={self.s_neg:.4f}"

        return {
            "value": round(cusum_val, 5),
            "confidence": round(confidence, 4),
            "triggered": triggered,
            "desc": desc
        }


class AmihudSignal(SignalChannel):
    """
    Amihud 非流动性因子 (Amihud Illiquidity Ratio)

    参考: Amihud, Y. (2002). "Illiquidity and stock returns"
    公式: ILLIQ = |return| / volume（单位成交量引起的价格变动）
    当 ILLIQ 急剧升高，意味着流动性骤降、市场脆弱性增强。
    """

    def __init__(self, surge_ratio: float = 3.0):
        """
        :param surge_ratio: 相对于历史均值的触发倍数
        """
        super().__init__("amihud", weight=0.2)
        self.surge_ratio = surge_ratio
        self.illiq_history = deque(maxlen=20)

    def compute(self, price, volume, ret, history) -> Dict:
        # 计算当前 Amihud 因子
        if volume <= 0:
            illiq = 0.0
        else:
            illiq = abs(ret) / (volume / 1e6)  # 将 volume 缩放到百万单位

        self.illiq_history.append(illiq)

        if len(self.illiq_history) < 3:
            return {"value": round(illiq, 6), "confidence": 0, "triggered": False, "desc": "Amihud 预热中"}

        hist = list(self.illiq_history)[:-1]
        mean_illiq = sum(hist) / len(hist)
        ratio = illiq / mean_illiq if mean_illiq > 0 else 1.0

        triggered = ratio > self.surge_ratio
        confidence = min((ratio - 1) / (self.surge_ratio * 2), 1.0) if ratio > 1 else 0.0

        return {
            "value": round(illiq, 6),
            "confidence": round(confidence, 4),
            "triggered": triggered,
            "desc": f"Amihud 非流动性激增 {ratio:.1f}x" if triggered else f"Amihud ratio={ratio:.2f}x"
        }


class VolumeSurgeSignal(SignalChannel):
    """成交量激增信号"""

    def __init__(self, surge_ratio: float = 3.0):
        super().__init__("volume_surge", weight=0.2)
        self.surge_ratio = surge_ratio

    def compute(self, price, volume, ret, history) -> Dict:
        volumes = history.get("volumes", [])
        if len(volumes) < 3:
            return {"value": 1.0, "confidence": 0, "triggered": False, "desc": "量比预热中"}

        mean_vol = sum(volumes) / len(volumes)
        ratio = volume / mean_vol if mean_vol > 0 else 1.0

        triggered = ratio > self.surge_ratio
        confidence = min((ratio - 1) / (self.surge_ratio * 3), 1.0) if ratio > 1 else 0.0

        return {
            "value": round(ratio, 2),
            "confidence": round(confidence, 4),
            "triggered": triggered,
            "desc": f"成交量激增 {ratio:.1f}x (阈值{self.surge_ratio}x)" if triggered else f"量比={ratio:.1f}x"
        }


class MultiSignalDetector:
    """
    多维信号融合异动检测器

    核心算法：贝叶斯后验概率更新
    P(A|signals) = P(A) * ∏ P(signal_i|A) / P(signal_i)

    采用对数似然比的累积计算以避免数值下溢。
    """

    def __init__(self, window_size: int = 10, prior_anomaly: float = 0.05,
                 z_threshold: float = 2.0, cusum_drift: float = 0.005,
                 cusum_h: float = 0.02, volume_surge: float = 3.0,
                 amihud_surge: float = 3.0, posterior_threshold: float = 0.6):
        """
        :param window_size: 滑动窗口大小
        :param prior_anomaly: 异动先验概率（市场基准异动率）
        :param posterior_threshold: 后验概率触发阈值
        """
        self.window_size = window_size
        self.prior = prior_anomaly
        self.posterior_threshold = posterior_threshold

        # 滑动窗口
        self.price_window = deque(maxlen=window_size)
        self.volume_window = deque(maxlen=window_size)
        self.return_window = deque(maxlen=window_size)
        self.last_price: Optional[float] = None
        self.tick_count = 0

        # 初始化信号通道
        self.signals: List[SignalChannel] = [
            ZScoreSignal(threshold=z_threshold),
            CUSUMSignal(drift=cusum_drift, threshold_h=cusum_h),
            AmihudSignal(surge_ratio=amihud_surge),
            VolumeSurgeSignal(surge_ratio=volume_surge),
        ]

    def feed(self, price: float, volume: float) -> Dict:
        """
        输入一个新 Tick，返回多信号融合检测结果。

        :return: {
            is_anomaly, anomaly_probability, anomaly_score,
            signals: {name: {value, confidence, triggered, desc}},
            detection_method, current_return, ...
        }
        """
        self.tick_count += 1

        # 计算收益率
        current_return = 0.0
        if self.last_price and self.last_price > 0:
            current_return = (price - self.last_price) / self.last_price

        # 更新窗口（排除当前值用于信号计算）
        history = {
            "returns": list(self.return_window),
            "volumes": list(self.volume_window),
            "prices": list(self.price_window),
        }

        self.price_window.append(price)
        self.volume_window.append(volume)
        self.return_window.append(current_return)
        self.last_price = price

        # 数据不足时跳过检测
        if len(self.return_window) < max(3, self.window_size // 2):
            return self._build_result(
                is_anomaly=False,
                probability=0.0,
                score=0.0,
                signals={},
                current_return=current_return,
                method="数据预热中"
            )

        # ---- 各通道独立检测 ---- #
        signal_results = {}
        for signal in self.signals:
            signal_results[signal.name] = signal.compute(price, volume, current_return, history)

        # ---- 贝叶斯后验融合 ---- #
        posterior = self._bayesian_fusion(signal_results)

        # ---- 综合评分 (0-100) ---- #
        score = self._compute_score(signal_results)

        # 判定：三通道触发
        # 1) 贝叶斯后验（单tick突变场景）
        # 2) 综合评分（多信号协同场景）
        # 3) 累积收益率偏离（渐进式拉升/闪崩场景）
        cumulative_trigger = False
        if len(self.return_window) >= 3:
            recent_returns = list(self.return_window)[-5:]  # 最近5个tick
            cum_ret = sum(recent_returns)
            if abs(cum_ret) > 0.005:  # 累积涨跌幅超过0.5%
                cumulative_trigger = True

        is_anomaly = (
            posterior > self.posterior_threshold
            or score > 15
            or cumulative_trigger
        )

        # 生成检测方法描述
        triggered_methods = [
            sr["desc"] for name, sr in signal_results.items() if sr["triggered"]
        ]
        if cumulative_trigger:
            cum_pct = sum(list(self.return_window)[-5:]) * 100
            triggered_methods.append(f"累积偏离 {cum_pct:+.2f}%")
        method = " ⊕ ".join(triggered_methods) if triggered_methods else "多信号平稳"

        return self._build_result(
            is_anomaly=is_anomaly,
            probability=posterior,
            score=score,
            signals=signal_results,
            current_return=current_return,
            method=method
        )

    def _bayesian_fusion(self, signal_results: Dict) -> float:
        """
        贝叶斯多信号融合

        使用对数似然比避免数值下溢：
        log-odds(A|signals) = log-odds(A) + Σ w_i * log(P(signal_i|A) / P(signal_i|¬A))
        """
        # 先验对数赔率
        prior_odds = self.prior / (1 - self.prior)
        log_odds = math.log(prior_odds + 1e-10)

        for signal in self.signals:
            result = signal_results.get(signal.name, {})
            confidence = result.get("confidence", 0.0)

            # 似然比: 信号越强，异动的似然越高
            # P(signal|anomaly) ≈ confidence
            # P(signal|normal) ≈ 1 - confidence
            p_signal_given_anomaly = max(confidence, 0.01)
            p_signal_given_normal = max(1 - confidence, 0.01)

            likelihood_ratio = p_signal_given_anomaly / p_signal_given_normal
            log_odds += signal.weight * math.log(likelihood_ratio + 1e-10)

        # 转回概率
        odds = math.exp(min(log_odds, 10))  # 防溢出
        posterior = odds / (1 + odds)

        return round(posterior, 4)

    def _compute_score(self, signal_results: Dict) -> float:
        """综合异动评分 (0-100)，加权各信号置信度"""
        total_weight = sum(s.weight for s in self.signals)
        weighted_sum = 0.0

        for signal in self.signals:
            result = signal_results.get(signal.name, {})
            weighted_sum += signal.weight * result.get("confidence", 0.0)

        score = (weighted_sum / total_weight) * 100 if total_weight > 0 else 0
        return round(min(score, 100), 1)

    def _build_result(self, is_anomaly: bool, probability: float, score: float,
                      signals: Dict, current_return: float, method: str) -> Dict:
        """构建标准化检测结果"""
        # 兼容旧接口字段
        z_val = signals.get("z_score", {}).get("value", 0)
        vol_ratio = signals.get("volume_surge", {}).get("value", 1.0)

        return {
            "is_anomaly": is_anomaly,
            "anomaly_probability": probability,
            "anomaly_score": score,
            "z_score": z_val,
            "volume_ratio": vol_ratio,
            "current_return": round(current_return * 100, 4),
            "detection_method": method,
            "signals": {
                name: {
                    "value": r.get("value", 0),
                    "confidence": r.get("confidence", 0),
                    "triggered": r.get("triggered", False),
                    "desc": r.get("desc", ""),
                }
                for name, r in signals.items()
            },
            "window_size": self.window_size,
            "posterior_threshold": self.posterior_threshold,
            "tick_count": self.tick_count,
        }

    def reset(self):
        """重置检测器状态"""
        self.price_window.clear()
        self.volume_window.clear()
        self.return_window.clear()
        self.last_price = None
        self.tick_count = 0
        # 重置 CUSUM 状态
        for s in self.signals:
            if isinstance(s, CUSUMSignal):
                s.s_pos = 0.0
                s.s_neg = 0.0
            elif isinstance(s, AmihudSignal):
                s.illiq_history.clear()
