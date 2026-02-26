"""
prepare_frontend_data.py — 前端数据预处理脚本
将 82MB 的 uav_trajectories.csv 预处理为紧凑的 JSON 文件，
大幅减少前端加载时间。

输入: data/processed/uav_trajectories.csv  (82MB, 766K行, 5093条轨迹)
输出: frontend/public/data/uav_trajectories.json (~5-8MB, 确定性采样20%)

优化策略:
  1. 服务端完成 CSV 解析和分组（不再由浏览器做）
  2. 确定性采样 20%（基于 flight_id hash，可复现）
  3. 只保留前端需要的字段: path + timestamps
  4. 坐标精度裁剪: lon/lat→6位, alt→整数, timestamp→3位
  5. 时间戳归一化: 相对于全局最小值（避免浮点精度丢失）
"""

import csv
import json
import hashlib
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FrontendDataPrep")

# 采样比例
SAMPLE_RATIO = 0.20
# 高度放大倍数（与前端 MapContainer.tsx 一致）
ALT_SCALE = 3


def deterministic_sample(flight_id: str, ratio: float) -> bool:
    """基于 flight_id 的确定性采样，保证每次运行结果一致"""
    h = hashlib.md5(f"sample_{flight_id}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) < ratio


def main():
    base = Path(__file__).resolve().parent.parent
    input_csv = base / "data" / "processed" / "uav_trajectories.csv"
    output_json = base / "frontend" / "public" / "data" / "uav_trajectories.json"

    if not input_csv.exists():
        logger.error(f"❌ 输入文件不存在: {input_csv}")
        return

    # 第一遍：读取并按 flight_id 分组
    logger.info(f"读取 CSV: {input_csv}")
    groups: dict[str, dict] = {}
    global_min_ts = float('inf')
    global_max_ts = float('-inf')
    row_count = 0

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row.get('flight_id', '')
            ts_str = row.get('timestamp', '')
            if not fid or not ts_str:
                continue

            ts = float(ts_str)
            lon = float(row['lon'])
            lat = float(row['lat'])
            alt = float(row.get('alt_rel', '50'))

            if fid not in groups:
                groups[fid] = {'path': [], 'timestamps': []}

            groups[fid]['path'].append([
                round(lon, 6),
                round(lat, 6),
                int(alt * ALT_SCALE)  # 高度放大并取整，节省字节
            ])
            groups[fid]['timestamps'].append(ts)

            if ts < global_min_ts:
                global_min_ts = ts
            if ts > global_max_ts:
                global_max_ts = ts

            row_count += 1
            if row_count % 200000 == 0:
                logger.info(f"  已读取 {row_count} 行...")

    logger.info(f"CSV 读取完成: {row_count} 行, {len(groups)} 条轨迹")
    logger.info(f"时间范围: {global_min_ts} ~ {global_max_ts} ({global_max_ts - global_min_ts:.0f}秒)")

    # 第二遍：确定性采样 + 时间戳归一化
    sampled = []
    for fid, data in groups.items():
        if not deterministic_sample(fid, SAMPLE_RATIO):
            continue
        # 归一化时间戳
        sampled.append({
            'id': fid,
            'path': data['path'],
            'timestamps': [round(t - global_min_ts, 3) for t in data['timestamps']]
        })

    logger.info(f"确定性采样 {SAMPLE_RATIO*100:.0f}%: {len(sampled)} / {len(groups)} 条轨迹")

    # 输出 JSON
    output_data = {
        'timeRange': {
            'min': 0,
            'max': round(global_max_ts - global_min_ts, 3)
        },
        'totalFlights': len(groups),
        'sampledFlights': len(sampled),
        'trajectories': sampled
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, separators=(',', ':'))  # 紧凑格式

    size_mb = output_json.stat().st_size / (1024 * 1024)
    logger.info(f"✅ 输出完成: {output_json}")
    logger.info(f"   文件大小: {size_mb:.2f} MB (原始 CSV: {input_csv.stat().st_size / (1024*1024):.2f} MB)")
    logger.info(f"   压缩比: {size_mb / (input_csv.stat().st_size / (1024*1024)) * 100:.1f}%")


if __name__ == "__main__":
    logger.info("=========== 开始前端数据预处理 ===========")
    main()
    logger.info("=========== 预处理完成 ===========")
