"""
process_trajectories.py — UAV 轨迹数据清洗与城市映射脚本
将 HF 正规数据集 (riotu-lab/Synthetic-UAV-Flight-Trajectories) 的原始轨迹
清洗、推导物理量、并平移映射到深圳南山区真实 POI 坐标上。

输入:
  - data/raw/uav_trajectories_raw.csv         (HF 原始数据: timestamp, tx, ty, tz)
  - data/processed/poi_demand.geojson          (需求 POI 作为起降锚点池)

输出:
  - data/processed/uav_trajectories.csv        (字段遵循 Data_Dictionary.md)

算法:
  1. 读取原始 CSV，按时间间隔 >1s 自动切分为独立轨迹
  2. 有限差分推导: speed_x/y/z, yaw, pitch, roll, battery_rem
  3. 平移映射: 将局部 x/y 坐标线性映射到 POI 对之间的 WGS84 经纬度
  4. 高度映射: 原始 z 归一化后映射到 50-120m 合理飞行高度

不使用 shapely/geopandas，纯 Python + math + csv 实现
"""

import csv
import json
import math
import hashlib
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TrajectoryProcessor")

# ============= 物理参数 =============
# 电池消耗系数: 每秒在单位速度²下的消耗百分比
BATTERY_DRAIN_COEFF = 0.0003
# 飞行高度映射范围 (米)
ALT_MIN = 50.0
ALT_MAX = 120.0
# 经纬度换算常量
METERS_PER_DEG_LAT = 111320.0
# 时间间隔阈值: 超过此值视为新轨迹
TRAJECTORY_GAP_SECONDS = 1.0
# 最小轨迹点数 (过短的丢弃)
MIN_TRAJECTORY_POINTS = 10
# roll 响应系数 (偏航角变化率 -> 滚转角)
ROLL_RESPONSE_COEFF = 0.3


def load_poi_anchors(poi_path: Path) -> list:
    """加载 POI 需求点作为轨迹起降锚点池，返回 [(lat, lon, name), ...]"""
    logger.info(f"加载 POI 锚点: {poi_path}")
    with open(poi_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    anchors = []
    for feat in data['features']:
        coords = feat['geometry']['coordinates']  # [lon, lat]
        name = feat['properties'].get('name', '')
        anchors.append((coords[1], coords[0], name))  # (lat, lon, name)

    logger.info(f"  可用锚点数: {len(anchors)}")
    return anchors


def deterministic_pair(flight_id: int, anchors: list) -> tuple:
    """
    基于 flight_id 确定性选择起终点 POI 对。
    使用 hash 保证可复现且不重复。
    """
    n = len(anchors)
    h = hashlib.md5(f"start_{flight_id}".encode()).hexdigest()
    start_idx = int(h[:8], 16) % n

    h2 = hashlib.md5(f"end_{flight_id}".encode()).hexdigest()
    end_idx = int(h2[:8], 16) % n
    # 确保起终点不同
    if end_idx == start_idx:
        end_idx = (end_idx + 1) % n

    return anchors[start_idx], anchors[end_idx]


def split_trajectories(rows: list) -> list:
    """
    按时间间隔 >1s 将原始数据切分为独立轨迹。
    返回 [[(timestamp, tx, ty, tz), ...], ...]
    """
    if not rows:
        return []

    trajectories = []
    current = [rows[0]]

    for i in range(1, len(rows)):
        dt = rows[i][0] - rows[i - 1][0]
        if dt > TRAJECTORY_GAP_SECONDS or dt < 0:
            if len(current) >= MIN_TRAJECTORY_POINTS:
                trajectories.append(current)
            current = []
        current.append(rows[i])

    if len(current) >= MIN_TRAJECTORY_POINTS:
        trajectories.append(current)

    return trajectories


def process_single_trajectory(traj: list, flight_id: int,
                              start_anchor: tuple, end_anchor: tuple) -> list:
    """
    处理单条轨迹:
    1. 有限差分推导速度
    2. 速度向量推导姿态角
    3. 能耗模型推导电量
    4. 平移映射到 WGS84

    返回: [dict, dict, ...] 每个 dict 是一行输出记录
    """
    n = len(traj)
    if n < 2:
        return []

    start_lat, start_lon, _ = start_anchor
    end_lat, end_lon, _ = end_anchor

    # 计算原始轨迹的 x/y 范围
    xs = [p[1] for p in traj]
    ys = [p[2] for p in traj]
    zs = [p[3] for p in traj]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    z_min, z_max = min(zs), max(zs)

    x_range = x_max - x_min if x_max != x_min else 1.0
    y_range = y_max - y_min if y_max != y_min else 1.0
    z_range = z_max - z_min if z_max != z_min else 1.0

    # 经纬度映射参数
    cos_lat = math.cos(math.radians((start_lat + end_lat) / 2))
    meters_per_deg_lon = METERS_PER_DEG_LAT * cos_lat

    records = []
    battery = 100.0
    prev_yaw = 0.0

    for i in range(n):
        t, tx, ty, tz = traj[i]

        # --- 平移映射到 WGS84 ---
        # 将局部坐标线性插值到起终点之间
        ratio_x = (tx - x_min) / x_range
        ratio_y = (ty - y_min) / y_range
        ratio_z = (tz - z_min) / z_range

        lat = start_lat + ratio_x * (end_lat - start_lat)
        lon = start_lon + ratio_y * (end_lon - start_lon)
        alt_abs = ALT_MIN + ratio_z * (ALT_MAX - ALT_MIN)
        alt_rel = alt_abs  # 起飞点假设为地面

        # --- 有限差分推导速度 ---
        if i < n - 1:
            dt = traj[i + 1][0] - t
            if dt <= 0:
                dt = 0.05  # 防除零
            speed_x = (traj[i + 1][1] - tx) / dt
            speed_y = (traj[i + 1][2] - ty) / dt
            speed_z = (traj[i + 1][3] - tz) / dt
        elif i > 0:
            dt = t - traj[i - 1][0]
            if dt <= 0:
                dt = 0.05
            speed_x = (tx - traj[i - 1][1]) / dt
            speed_y = (ty - traj[i - 1][2]) / dt
            speed_z = (tz - traj[i - 1][3]) / dt
        else:
            speed_x = speed_y = speed_z = 0.0
            dt = 0.05

        # --- 姿态角推导 ---
        # 偏航角 (yaw): 水平速度方向
        h_speed = math.sqrt(speed_x ** 2 + speed_y ** 2)
        if h_speed > 0.01:
            yaw = math.degrees(math.atan2(speed_y, speed_x))
        else:
            yaw = prev_yaw

        # 俯仰角 (pitch): 爬升/下降角
        total_h_speed = max(h_speed, 0.01)
        pitch = math.degrees(math.atan2(speed_z, total_h_speed))

        # 滚转角 (roll): 基于偏航角变化率 (转弯倾斜)
        yaw_rate = yaw - prev_yaw
        # 处理 ±180° 跳变
        if yaw_rate > 180:
            yaw_rate -= 360
        elif yaw_rate < -180:
            yaw_rate += 360
        roll = max(-45, min(45, yaw_rate * ROLL_RESPONSE_COEFF))
        prev_yaw = yaw

        # --- 电量消耗模型 ---
        v_squared = speed_x ** 2 + speed_y ** 2 + speed_z ** 2
        battery -= BATTERY_DRAIN_COEFF * v_squared * dt
        battery = max(battery, 5.0)  # 不低于 5%

        records.append({
            'flight_id': f"UAV_{flight_id:05d}",
            'timestamp': round(t, 3),
            'lat': round(lat, 7),
            'lon': round(lon, 7),
            'alt_abs': round(alt_abs, 2),
            'alt_rel': round(alt_rel, 2),
            'speed_x': round(speed_x, 4),
            'speed_y': round(speed_y, 4),
            'speed_z': round(speed_z, 4),
            'roll': round(roll, 2),
            'pitch': round(pitch, 2),
            'yaw': round(yaw, 2),
            'battery_rem': round(battery, 2),
        })

    return records


def process_trajectories(raw_csv: Path, poi_path: Path, output_csv: Path):
    """主处理流程"""
    # 1. 加载 POI 锚点
    anchors = load_poi_anchors(poi_path)
    if len(anchors) < 2:
        logger.error("POI 锚点不足 2 个，无法进行平移映射")
        return

    # 2. 读取原始 CSV
    logger.info(f"读取原始轨迹: {raw_csv}")
    rows = []
    with open(raw_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append((
                    float(row['timestamp']),
                    float(row['tx']),
                    float(row['ty']),
                    float(row['tz']),
                ))
            except (ValueError, KeyError):
                continue

    logger.info(f"原始数据行数: {len(rows)}")

    # 3. 切分轨迹
    logger.info("按时间间隔切分轨迹...")
    trajectories = split_trajectories(rows)
    logger.info(f"切分为 {len(trajectories)} 条独立轨迹")

    # 4. 逐条处理
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'flight_id', 'timestamp', 'lat', 'lon',
        'alt_abs', 'alt_rel', 'speed_x', 'speed_y', 'speed_z',
        'roll', 'pitch', 'yaw', 'battery_rem'
    ]

    total_records = 0
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, traj in enumerate(trajectories):
            start_anchor, end_anchor = deterministic_pair(idx, anchors)
            records = process_single_trajectory(
                traj, idx, start_anchor, end_anchor
            )
            writer.writerows(records)
            total_records += len(records)

            if (idx + 1) % 500 == 0:
                logger.info(f"  已处理 {idx + 1}/{len(trajectories)} 条轨迹...")

    size_mb = output_csv.stat().st_size / (1024 * 1024)
    logger.info(f"✅ 轨迹处理完成: {output_csv}")
    logger.info(f"   轨迹总数: {len(trajectories)}")
    logger.info(f"   记录总行数: {total_records}")
    logger.info(f"   文件大小: {size_mb:.2f} MB")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent

    raw_csv = base / "data" / "raw" / "uav_trajectories_raw.csv"
    poi_path = base / "data" / "processed" / "poi_demand.geojson"
    output_csv = base / "data" / "processed" / "uav_trajectories.csv"

    if not raw_csv.exists():
        logger.error(f"❌ 原始数据不存在: {raw_csv}")
        logger.info("请先运行 fetch_uav_trajectories.py 下载 HF 数据集")
        exit(1)

    if not poi_path.exists():
        logger.error(f"❌ POI 数据不存在: {poi_path}")
        logger.info("请先运行 process_pois.py 生成需求 POI")
        exit(1)

    logger.info("=========== 开始 UAV 轨迹清洗与城市映射 ===========")
    process_trajectories(raw_csv, poi_path, output_csv)
    logger.info("=========== 轨迹处理完成 ===========")
