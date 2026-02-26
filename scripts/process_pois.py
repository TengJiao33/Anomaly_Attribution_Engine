"""
process_pois.py — POI 数据清洗脚本
将两类 POI 原始 JSON 转换为标准 GeoJSON

输入:
  - data/raw/poi_sensitive_raw.json (医院/学校/公安 -> 禁飞区)
  - data/raw/poi_demand_raw.json   (写字楼/住宅 -> 机坪需求点)

输出:
  - data/processed/poi_sensitive.geojson (Polygon, 含100m禁飞缓冲区)
  - data/processed/poi_demand.geojson    (Point, 含需求热力权重)

不使用 shapely/geopandas，纯 Python + math 实现 Buffer 膨胀
"""

import json
import math
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("POIProcessor")

# ============ 权重配置 ============

SENSITIVE_WEIGHTS = {
    'hospital': 10,
    'clinic': 7,
    'school': 8,
    'kindergarten': 8,
    'college': 7,
    'university': 9,
    'police': 6,
}

DEMAND_WEIGHTS = {
    'commercial': 5,
    'office': 6,
    'residential': 3,
    'apartments': 4,
}

# 禁飞缓冲区半径 (米)
BUFFER_RADIUS_M = 100
# 近似圆的边数
BUFFER_SEGMENTS = 32


def extract_coords(element: dict) -> tuple | None:
    """
    从 Overpass 元素中提取经纬度。
    node 类型 -> (lat, lon)
    way 类型 -> center.(lat, lon)
    """
    if element['type'] == 'node':
        return (element.get('lat'), element.get('lon'))
    elif element['type'] == 'way':
        center = element.get('center')
        if center:
            return (center.get('lat'), center.get('lon'))
    return None


def create_circle_polygon(lat: float, lon: float,
                          radius_m: float, segments: int = 32) -> list:
    """
    生成以 (lat, lon) 为圆心、radius_m 为半径的近似圆形 Polygon 坐标环。
    纯数学计算，不依赖空间库。

    经纬度换算:
    - 1° lat ≈ 111320m
    - 1° lon ≈ 111320m × cos(lat)
    """
    lat_rad = math.radians(lat)
    d_lat = radius_m / 111320.0
    d_lon = radius_m / (111320.0 * math.cos(lat_rad))

    coords = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        pt_lon = lon + d_lon * math.cos(angle)
        pt_lat = lat + d_lat * math.sin(angle)
        coords.append([round(pt_lon, 7), round(pt_lat, 7)])

    # 闭合环
    coords.append(coords[0])
    return coords


def classify_amenity(tags: dict) -> str:
    """从 tags 中提取 amenity 类型"""
    return tags.get('amenity', 'unknown')


def classify_building(tags: dict) -> str:
    """从 tags 中提取 building 类型"""
    return tags.get('building', 'unknown')


def process_sensitive_pois(input_path: Path, output_path: Path):
    """处理敏感 POI: 提取坐标 + 生成禁飞缓冲区 Polygon"""
    logger.info(f"读取敏感 POI: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    elements = raw.get('elements', [])
    logger.info(f"原始敏感 POI 数量: {len(elements)}")

    features = []
    skipped = 0

    for elem in elements:
        coords = extract_coords(elem)
        if coords is None or coords[0] is None:
            skipped += 1
            continue

        lat, lon = coords
        tags = elem.get('tags', {})
        poi_type = classify_amenity(tags)
        weight = SENSITIVE_WEIGHTS.get(poi_type, 5)

        # 生成 100m 缓冲区圆形 Polygon
        ring = create_circle_polygon(lat, lon, BUFFER_RADIUS_M, BUFFER_SEGMENTS)

        feature = {
            "type": "Feature",
            "properties": {
                "poi_id": str(elem['id']),
                "name": tags.get('name', ''),
                "type": poi_type,
                "weight": weight,
                "buffer_radius_m": BUFFER_RADIUS_M,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring]
            }
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"✅ 敏感 POI 处理完成: {output_path}")
    logger.info(f"   特征数: {len(features)}, 跳过: {skipped}")
    logger.info(f"   文件大小: {size_mb:.2f} MB")


def process_demand_pois(input_path: Path, output_path: Path):
    """处理需求 POI: 提取坐标 + 赋需求权重 (Point)"""
    logger.info(f"读取需求 POI: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    elements = raw.get('elements', [])
    logger.info(f"原始需求 POI 数量: {len(elements)}")

    features = []
    skipped = 0

    for elem in elements:
        coords = extract_coords(elem)
        if coords is None or coords[0] is None:
            skipped += 1
            continue

        lat, lon = coords
        tags = elem.get('tags', {})
        poi_type = classify_building(tags)
        weight = DEMAND_WEIGHTS.get(poi_type, 3)

        feature = {
            "type": "Feature",
            "properties": {
                "poi_id": str(elem['id']),
                "name": tags.get('name', ''),
                "type": poi_type,
                "weight": weight,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 7), round(lat, 7)]
            }
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"✅ 需求 POI 处理完成: {output_path}")
    logger.info(f"   特征数: {len(features)}, 跳过: {skipped}")
    logger.info(f"   文件大小: {size_mb:.2f} MB")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    raw_dir = base / "data" / "raw"
    proc_dir = base / "data" / "processed"

    logger.info("=========== 开始 POI 数据清洗 ===========")

    process_sensitive_pois(
        raw_dir / "poi_sensitive_raw.json",
        proc_dir / "poi_sensitive.geojson"
    )

    process_demand_pois(
        raw_dir / "poi_demand_raw.json",
        proc_dir / "poi_demand.geojson"
    )

    logger.info("=========== POI 清洗完成 ===========")
