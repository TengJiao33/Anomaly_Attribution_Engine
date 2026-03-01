"""
fetch_multi_city_data.py — 多城市建筑与POI数据统一获取脚本 (v2)

策略: 按行政区名称使用 Overpass area 查询, 精确匹配行政区边界
不再使用矩形 BBox + 瓦片分割

支持城市: 深圳(已有)、重庆、北京、上海、广州、成都
数据源: Overpass API (OpenStreetMap)
输出: data/raw/{city}_buildings_raw.json, data/raw/{city}_poi_*.json
"""
import os
import sys
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("MultiCityFetcher")

# ===========================================================================
#  城市配置: 按行政区名称查询, 不再使用 BBox
# ===========================================================================
CITY_CONFIG = {
    "shenzhen": {
        "name": "深圳南山",
        "districts": ["南山区"],
        "admin_level": "8",
        "parent_area": "深圳市",
        "desc": "南山区 (已有数据, 默认跳过)",
        # 保留 bbox 仅用于 POI 查询的后备
        "bbox": (22.48, 113.88, 22.58, 113.98),
    },
    "chongqing": {
        "name": "重庆主城",
        "districts": ["渝中区", "南岸区", "江北区", "沙坪坝区"],
        "admin_level": "8",
        "parent_area": "重庆市",
        "desc": "渝中+南岸+江北+沙坪坝核心区",
        "bbox": (29.45, 106.40, 29.68, 106.68),
    },
    "beijing": {
        "name": "北京核心",
        "districts": ["朝阳区", "海淀区", "西城区", "东城区"],
        "admin_level": "8",
        "parent_area": "北京市",
        "desc": "朝阳+海淀+西城+东城核心区",
        "bbox": (39.87, 116.28, 39.98, 116.48),
    },
    "shanghai": {
        "name": "上海核心",
        "districts": ["浦东新区", "静安区", "黄浦区"],
        "admin_level": "8",
        "parent_area": "上海市",
        "desc": "浦东+静安+黄浦",
        "bbox": (31.17, 121.42, 31.28, 121.53),
    },
    "guangzhou": {
        "name": "广州核心",
        "districts": ["天河区", "越秀区", "海珠区"],
        "admin_level": "8",
        "parent_area": "广州市",
        "desc": "天河+越秀+海珠",
        "bbox": (23.08, 113.22, 23.18, 113.33),
    },
    "chengdu": {
        "name": "成都核心",
        "districts": ["锦江区", "武侯区", "高新区"],
        "admin_level": "8",
        "parent_area": "成都市",
        "desc": "锦江+武侯+高新区",
        "bbox": (30.57, 103.98, 30.68, 104.12),
    },
}

OVERPASS_URL = "http://overpass-api.de/api/interpreter"


def ensure_deps():
    for lib in ["requests"]:
        try:
            __import__(lib)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])


# ===========================================================================
#  Overpass 请求工具
# ===========================================================================
def _overpass_request(query: str, retries: int = 4, timeout: int = 300):
    """带重试的 Overpass API 请求, 超时时间更长以适配大区域查询"""
    import requests
    for attempt in range(retries):
        try:
            logger.info(f"    📡 发送 Overpass 请求 (第{attempt+1}次, 超时{timeout}s)...")
            resp = requests.post(OVERPASS_URL, data={'data': query}, timeout=timeout)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                logger.warning(f"    ⏳ Overpass 限流, 等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            if resp.status_code == 504:
                wait = 20 * (attempt + 1)
                logger.warning(f"    ⏳ 网关超时 504, 等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"    ⏳ 请求超时 (第{attempt+1}次), 重试...")
            time.sleep(15)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"    ⚠️  请求失败: {e}, 重试...")
                time.sleep(15)
            else:
                raise
    return None


# ===========================================================================
#  建筑数据获取 — 按行政区查询
# ===========================================================================
def fetch_buildings(city_key: str, output_dir: Path) -> bool:
    """按行政区名称获取建筑数据, 逐区查询后合并去重"""
    config = CITY_CONFIG[city_key]
    output_file = output_dir / f"{city_key}_buildings_raw.json"

    logger.info(f"  🏗️  获取 {config['name']} 建筑数据...")
    logger.info(f"     目标行政区: {', '.join(config['districts'])}")

    all_elements = []
    seen_ids = set()
    failed_districts = []

    for idx, district in enumerate(config['districts']):
        logger.info(f"     📦 [{idx+1}/{len(config['districts'])}] 查询 {district}...")

        # 使用 area 查询: 通过行政区名称 + admin_level 精确匹配
        # 对于某些特殊区（如"高新区"不是标准行政区划），使用 bbox 后备
        query = _build_district_query(district, config)

        try:
            data = _overpass_request(query, timeout=600)
            if data:
                new_count = 0
                for el in data.get('elements', []):
                    eid = el.get('id', 0)
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        all_elements.append(el)
                        new_count += 1
                total_in_response = len(data.get('elements', []))
                dup_count = total_in_response - new_count
                logger.info(f"        ✅ {district}: +{new_count} 新元素"
                            f" (重复跳过: {dup_count}, 累计: {len(all_elements)})")
            else:
                logger.warning(f"        ⚠️  {district}: 请求返回空")
                failed_districts.append(district)
        except Exception as ex:
            logger.warning(f"        ⚠️  {district} 查询失败: {ex}")
            failed_districts.append(district)

        # 区与区之间等待, 避免 Overpass 限流
        if idx < len(config['districts']) - 1:
            wait = 12
            logger.info(f"        ⏳ 等待 {wait}s 后查询下一个区...")
            time.sleep(wait)

    if failed_districts:
        logger.warning(f"  ⚠️  以下区域查询失败: {', '.join(failed_districts)}")

    if not all_elements:
        logger.error(f"  ❌ 建筑数据获取失败: 所有区域均未返回数据")
        return False

    result = {"elements": all_elements}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)

    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    logger.info(f"  📊 总计 {len(all_elements)} 个建筑元素 (去重后)")
    logger.info(f"  ✅ 已保存: {output_file.name} ({size_mb:.1f} MB)")
    return True


def _build_district_query(district: str, config: dict) -> str:
    """
    构建 Overpass 查询语句。
    优先使用 area 查询 (按行政区名称)，对于非标准行政区使用 bbox 后备。

    注意: 不指定 admin_level，因为直辖市(重庆/上海/北京)的市辖区
    admin_level=6，而普通省会城市的区 admin_level=8，无法统一。
    仅按名称匹配 area 即可，因为行政区名称（如"渝中区""静安区"）
    在全国范围内基本唯一。
    """
    # 某些非标准区划（如 "高新区"）在 OSM 中可能没有行政边界
    # 这些情况使用 bbox 后备查询
    non_standard_districts = ["高新区", "高新技术产业开发区"]
    if district in non_standard_districts:
        logger.info(f"        ℹ️  {district} 非标准行政区划, 使用 bbox 后备查询")
        bbox = config.get("bbox")
        if bbox:
            s, w, n, e = bbox
            return f"""
            [out:json][timeout:600][maxsize:1073741824];
            (
              way["building"]({s},{w},{n},{e});
              relation["building"]({s},{w},{n},{e});
            );
            out geom;
            """

    bbox = config.get("bbox")
    bbox_filter = f"({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]})" if bbox else ""

    # area 查询: 增加父级区域限制，防止全国重名区冲突（如宁波长春乱入）
    parent_area = config.get("parent_area", "")
    if parent_area:
        area_query = f'area["name"="{parent_area}"]->.city;\n    area["name"="{district}"](area.city)->.target;'
    else:
        area_query = f'area["name"="{district}"]["boundary"="administrative"]->.target;'

    query = f"""
    [out:json][timeout:600][maxsize:1073741824];
    {area_query}
    (
      way["building"](area.target){bbox_filter};
      relation["building"](area.target){bbox_filter};
    );
    out geom;
    """
    return query


# ===========================================================================
#  POI 数据获取 — 按行政区 area 查询（与建筑一致）
# ===========================================================================
def fetch_pois(city_key: str, output_dir: Path) -> bool:
    """按行政区获取敏感点和需求点 POI, 范围与建筑保持一致"""
    config = CITY_CONFIG[city_key]

    all_ok = True
    for poi_type in ["sensitive", "demand"]:
        output_file = output_dir / f"{city_key}_poi_{poi_type}_raw.json"

        if output_file.exists() and os.path.getsize(output_file) > 100:
            size_kb = os.path.getsize(output_file) / 1024
            logger.info(f"  ✅ {poi_type} POI 已存在: {output_file.name} ({size_kb:.0f} KB)")
            continue

        logger.info(f"  📍 获取 {config['name']} {poi_type} POI (按行政区)...")

        all_elements = []
        seen_ids = set()

        for idx, district in enumerate(config['districts']):
            logger.info(f"     📦 POI [{idx+1}/{len(config['districts'])}] {district}...")

            query = _build_poi_query_for_district(district, config, poi_type)

            try:
                data = _overpass_request(query, timeout=300)
                if data:
                    for el in data.get('elements', []):
                        eid = el.get('id', 0)
                        if eid not in seen_ids:
                            seen_ids.add(eid)
                            all_elements.append(el)
                    logger.info(f"        ✅ +{len(data.get('elements', []))} (累计去重: {len(all_elements)})")
            except Exception as ex:
                logger.warning(f"        ⚠️  {district} POI 查询失败: {ex}")

            if idx < len(config['districts']) - 1:
                time.sleep(8)

        if all_elements:
            result = {"elements": all_elements}
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)
            size_kb = os.path.getsize(output_file) / 1024
            logger.info(f"  📊 {poi_type} POI: {len(all_elements)} 个 (去重后)")
            logger.info(f"  ✅ 已保存: {output_file.name} ({size_kb:.0f} KB)")
        else:
            logger.error(f"  ❌ {poi_type} POI 获取失败: 所有区域均未返回数据")
            all_ok = False

        time.sleep(10)

    return all_ok


def _build_poi_query_for_district(district: str, config: dict, poi_type: str) -> str:
    """为单个行政区构建 POI 查询"""
    # 非标准行政区使用 bbox 后备
    non_standard_districts = ["高新区", "高新技术产业开发区"]
    if district in non_standard_districts:
        bbox = config.get("bbox")
        if not bbox:
            return ""
        s, w, n, e = bbox
        area_filter = f"({s},{w},{n},{e})"
    else:
        bbox = config.get("bbox")
        bbox_filter = f"({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]})" if bbox else ""
        area_filter = f"(area.target){bbox_filter}"

    # 构建查询头
    if district in non_standard_districts:
        query_head = f'[out:json][timeout:300][maxsize:1073741824];'
    else:
        parent_area = config.get("parent_area", "")
        if parent_area:
            query_head = f"""[out:json][timeout:300][maxsize:1073741824];
    area["name"="{parent_area}"]->.city;
    area["name"="{district}"](area.city)->.target;"""
        else:
            query_head = f"""[out:json][timeout:300][maxsize:1073741824];
    area["name"="{district}"]["boundary"="administrative"]->.target;"""

    if poi_type == "sensitive":
        return f"""
        {query_head}
        (
          node["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]{area_filter};
          way["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]{area_filter};
        );
        out center;
        """
    else:
        return f"""
        {query_head}
        (
          node["building"~"commercial|office|residential|apartments"]{area_filter};
          way["building"~"commercial|office|residential|apartments"]{area_filter};
          node["amenity"~"restaurant|cafe|fast_food|marketplace"]{area_filter};
          node["shop"~"supermarket|convenience|mall"]{area_filter};
        );
        out center;
        """


# ===========================================================================
#  主入口
# ===========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多城市建筑与POI数据统一获取 (v2: area查询)")
    parser.add_argument("--output", type=str, default="../data/raw",
                        help="原始数据输出目录")
    parser.add_argument("--cities", type=str, default="all",
                        help="要获取的城市, 逗号分隔或'all'. "
                             "可选: " + ", ".join(CITY_CONFIG.keys()))
    parser.add_argument("--buildings-only", action="store_true", default=False,
                        help="仅获取建筑数据, 跳过POI")
    parser.add_argument("--poi-only", action="store_true", default=False,
                        help="仅获取POI数据, 跳过建筑")
    args = parser.parse_args()

    output_path = Path(__file__).resolve().parent / args.output
    output_path.mkdir(parents=True, exist_ok=True)

    # 解析城市列表
    if args.cities.lower() == "all":
        # 默认跳过已有数据的深圳
        cities = [k for k in CITY_CONFIG if k != "shenzhen"]
    else:
        cities = [c.strip() for c in args.cities.split(",")]

    logger.info("=" * 60)
    logger.info("🏙️  多城市地理数据统一获取 (v2: 行政区精确查询)")
    logger.info(f"📁 输出目录: {output_path}")
    logger.info(f"🎯 目标城市: {', '.join(CITY_CONFIG[c]['name'] for c in cities if c in CITY_CONFIG)}")
    logger.info("=" * 60)

    ensure_deps()

    results = {}
    for i, city in enumerate(cities):
        if city not in CITY_CONFIG:
            logger.warning(f"未知城市: {city}, 跳过")
            continue

        config = CITY_CONFIG[city]
        logger.info("")
        logger.info(f"━━━ [{i+1}/{len(cities)}] {config['name']} ({config['desc']}) ━━━")

        bld_ok = True
        poi_ok = True

        # 获取建筑
        if not args.poi_only:
            bld_ok = fetch_buildings(city, output_path)
            time.sleep(10)

        # 获取 POI
        if not args.buildings_only:
            poi_ok = fetch_pois(city, output_path)

        results[config['name']] = bld_ok and poi_ok

        # 城市间间隔, 避免 Overpass 限流
        if i < len(cities) - 1:
            logger.info("  ⏳ 等待 15 秒后继续下一个城市...")
            time.sleep(15)

    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 获取结果汇总:")
    for city_name, ok in results.items():
        status = "✅ 成功" if ok else "⚠️  部分失败"
        logger.info(f"  {city_name}: {status}")
    logger.info("=" * 60)
