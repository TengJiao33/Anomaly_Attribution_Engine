"""
process_buildings.py — 建筑数据清洗脚本
将 Overpass API 原始 JSON 转换为标准 3D GeoJSON (FeatureCollection)

输入: data/raw/shenzhen_nanshan_buildings_raw.json
输出: data/processed/buildings_3d.geojson

算法:
1. 建立 Node 索引: {id -> (lat, lon)}
2. Way -> Polygon: 通过 node 引用组装坐标环
3. Relation -> MultiPolygon: 处理 outer/inner 成员
4. 高度赋值: 按建筑类型分层 + 确定性种子

不使用任何空间库 (shapely/geopandas)，纯 Python + math 实现
"""

import json
import hashlib
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BuildingProcessor")

# ============ 高度赋值策略 ============

# 按建筑类型划分的高度范围 (最小, 最大) 单位: 米
HEIGHT_RANGES = {
    'commercial':  (30, 80),
    'office':      (40, 120),
    'retail':      (10, 25),
    'industrial':  (8, 15),
    'warehouse':   (6, 12),
    'residential': (15, 50),
    'apartments':  (20, 60),
    'house':       (8, 15),
    'school':      (10, 25),
    'hospital':    (15, 40),
    'church':      (10, 30),
    'hotel':       (25, 80),
    'train_station': (10, 25),
    'garage':      (4, 8),
    'yes':         (10, 30),      # 通用类型
}
DEFAULT_HEIGHT_RANGE = (10, 30)


def deterministic_height(osm_id: int, min_h: float, max_h: float) -> float:
    """
    基于 osm_id 的确定性伪随机高度，保证可复现。
    使用 md5 hash 将 id 映射到 [min_h, max_h] 区间。
    """
    h = hashlib.md5(str(osm_id).encode()).hexdigest()
    ratio = int(h[:8], 16) / 0xFFFFFFFF
    return round(min_h + ratio * (max_h - min_h), 1)


def parse_height(tags: dict, osm_id: int) -> float:
    """
    从 tags 中提取或估算建筑高度。
    优先级: height > building:levels > 按类型确定性赋值
    """
    # 1. 直接有 height 标签
    raw_h = tags.get('height', '')
    if raw_h:
        try:
            return round(float(str(raw_h).replace('m', '').strip()), 1)
        except ValueError:
            pass

    # 2. 有层数标签 -> 每层 3m
    levels = tags.get('building:levels', '')
    if levels:
        try:
            return round(float(str(levels).strip()) * 3.0, 1)
        except ValueError:
            pass

    # 3. 按建筑类型确定性赋值
    building_type = tags.get('building', 'yes')
    h_range = HEIGHT_RANGES.get(building_type, DEFAULT_HEIGHT_RANGE)
    return deterministic_height(osm_id, h_range[0], h_range[1])


def build_node_index(elements: list) -> dict:
    """构建 node 索引: {id -> (lat, lon)}"""
    index = {}
    for e in elements:
        if e['type'] == 'node':
            index[e['id']] = (e['lat'], e['lon'])
    return index


def way_to_polygon(way: dict, node_index: dict) -> list | None:
    """
    将 way 转换为 GeoJSON 坐标环 [[lon, lat], ...]
    返回 None 表示节点缺失无法组装
    """
    coords = []
    for nid in way.get('nodes', []):
        pos = node_index.get(nid)
        if pos is None:
            return None  # 节点缺失，跳过
        coords.append([pos[1], pos[0]])  # GeoJSON 是 [lon, lat]

    # 确保闭合
    if len(coords) >= 3:
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords
    return None


def build_way_index(elements: list) -> dict:
    """构建 way 索引: {id -> way_element}，用于 relation 解析"""
    return {e['id']: e for e in elements if e['type'] == 'way'}


def relation_to_multipolygon(relation: dict, way_index: dict, node_index: dict) -> dict | None:
    """
    将 relation 转换为 GeoJSON MultiPolygon 或 Polygon。
    处理 outer/inner 成员。
    """
    outers = []
    inners = []

    for member in relation.get('members', []):
        if member['type'] != 'way':
            continue
        way = way_index.get(member['ref'])
        if way is None:
            continue
        ring = way_to_polygon(way, node_index)
        if ring is None:
            continue

        if member.get('role') == 'inner':
            inners.append(ring)
        else:  # outer 或无 role
            outers.append(ring)

    if not outers:
        return None

    # 简单策略: 如果只有一个 outer，将所有 inner 作为孔
    if len(outers) == 1:
        polygon = [outers[0]] + inners
        return {"type": "Polygon", "coordinates": polygon}
    else:
        # 多个 outer -> MultiPolygon (每个 outer 独立，暂不匹配 inner)
        polys = [[o] for o in outers]
        return {"type": "MultiPolygon", "coordinates": polys}


def process_buildings(input_path: Path, output_path: Path):
    """主处理流程"""
    logger.info(f"读取原始数据: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    elements = raw.get('elements', [])
    logger.info(f"原始元素总数: {len(elements)}")

    # 步骤1: 构建索引
    logger.info("构建 Node 索引...")
    node_index = build_node_index(elements)
    logger.info(f"  Node 数量: {len(node_index)}")

    way_index = build_way_index(elements)
    logger.info(f"  Way 数量: {len(way_index)}")

    relations = [e for e in elements if e['type'] == 'relation']
    logger.info(f"  Relation 数量: {len(relations)}")

    # 步骤2: 转换 Way -> Feature
    features = []
    skipped_ways = 0

    for way in way_index.values():
        tags = way.get('tags', {})
        if 'building' not in tags:
            continue  # 非建筑 way (可能是 relation 的子部件)

        ring = way_to_polygon(way, node_index)
        if ring is None:
            skipped_ways += 1
            continue

        height = parse_height(tags, way['id'])

        feature = {
            "type": "Feature",
            "properties": {
                "osm_id": str(way['id']),
                "name": tags.get('name', ''),
                "building": tags.get('building', 'yes'),
                "height": height,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring]
            }
        }
        features.append(feature)

    logger.info(f"Way 转换完成: {len(features)} 个建筑, 跳过 {skipped_ways} 个")

    # 步骤3: 转换 Relation -> Feature
    skipped_rels = 0
    for rel in relations:
        tags = rel.get('tags', {})
        if 'building' not in tags:
            continue

        geometry = relation_to_multipolygon(rel, way_index, node_index)
        if geometry is None:
            skipped_rels += 1
            continue

        height = parse_height(tags, rel['id'])

        feature = {
            "type": "Feature",
            "properties": {
                "osm_id": str(rel['id']),
                "name": tags.get('name', ''),
                "building": tags.get('building', 'yes'),
                "height": height,
            },
            "geometry": geometry
        }
        features.append(feature)

    logger.info(f"Relation 转换完成: 新增 {len(relations) - skipped_rels} 个, 跳过 {skipped_rels} 个")

    # 步骤4: 输出 GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"✅ 输出完成: {output_path}")
    logger.info(f"   建筑总数: {len(features)}")
    logger.info(f"   文件大小: {size_mb:.2f} MB")

    # 打印高度分布统计
    heights = [f['properties']['height'] for f in features]
    if heights:
        logger.info(f"   高度范围: {min(heights):.1f}m - {max(heights):.1f}m")
        avg_h = sum(heights) / len(heights)
        logger.info(f"   平均高度: {avg_h:.1f}m")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    input_file = base / "data" / "raw" / "shenzhen_nanshan_buildings_raw.json"
    output_file = base / "data" / "processed" / "buildings_3d.geojson"

    logger.info("=========== 开始建筑数据清洗 ===========")
    process_buildings(input_file, output_file)
    logger.info("=========== 建筑清洗完成 ===========")
