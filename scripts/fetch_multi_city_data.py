"""
fetch_multi_city_data.py — 多城市建筑与POI数据统一获取脚本

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
#  城市配置: (south, west, north, east)
# ===========================================================================
CITY_CONFIG = {
    "shenzhen": {
        "name": "深圳南山",
        "bbox": (22.48, 113.88, 22.58, 113.98),
        "desc": "南山区及周边 (已有数据, 默认跳过)"
    },
    "chongqing": {
        "name": "重庆主城",
        "bbox": (29.45, 106.40, 29.68, 106.68),
        "desc": "渝中+南岸+江北+沙坪坝核心区"
    },
    "beijing": {
        "name": "北京核心",
        "bbox": (39.87, 116.28, 39.98, 116.48),
        "desc": "朝阳+海淀+西城核心区"
    },
    "shanghai": {
        "name": "上海核心",
        "bbox": (31.17, 121.42, 31.28, 121.53),
        "desc": "浦东+静安+黄浦"
    },
    "guangzhou": {
        "name": "广州核心",
        "bbox": (23.08, 113.22, 23.18, 113.33),
        "desc": "天河+越秀+海珠"
    },
    "chengdu": {
        "name": "成都核心",
        "bbox": (30.57, 103.98, 30.68, 104.12),
        "desc": "锦江+武侯+高新区"
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
#  建筑数据获取
# ===========================================================================
def _overpass_request(query: str, retries: int = 3, timeout: int = 180):
    """带重试的 Overpass API 请求"""
    import requests
    for attempt in range(retries):
        try:
            resp = requests.post(OVERPASS_URL, data={'data': query}, timeout=timeout)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                logger.warning(f"    ⏳ Overpass 限流, 等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"    ⏳ 请求超时 (第{attempt+1}次), 重试...")
            time.sleep(10)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"    ⚠️  请求失败: {e}, 重试...")
                time.sleep(10)
            else:
                raise
    return None


def _split_bbox(bbox, tile_size=0.12):
    """将大BBox分割为小瓦片, 每块约 tile_size x tile_size 度"""
    south, west, north, east = bbox
    tiles = []
    lat = south
    while lat < north:
        lon = west
        while lon < east:
            t_n = min(lat + tile_size, north)
            t_e = min(lon + tile_size, east)
            tiles.append((lat, lon, t_n, t_e))
            lon += tile_size
        lat += tile_size
    return tiles


def fetch_buildings(city_key: str, output_dir: Path) -> bool:
    """获取指定城市的建筑footprint数据 (分块请求避免超时)"""
    config = CITY_CONFIG[city_key]
    bbox = config["bbox"]
    output_file = output_dir / f"{city_key}_buildings_raw.json"

    # 取消跳过已存在文件的逻辑，以保证能够重新获取最新格式
    # if output_file.exists() and os.path.getsize(output_file) > 1000:
    #     size_mb = os.path.getsize(output_file) / (1024 * 1024)
    #     logger.info(f"  ✅ 建筑数据已存在: {output_file.name} ({size_mb:.1f} MB)")
    #     return True

    logger.info(f"  🏗️  获取 {config['name']} 建筑数据...")
    logger.info(f"     BBox: S={bbox[0]}, W={bbox[1]}, N={bbox[2]}, E={bbox[3]}")

    # 将大 BBox 分割为小瓦片, 避免 Overpass 超时
    tiles = _split_bbox(bbox)
    logger.info(f"     分割为 {len(tiles)} 个瓦片请求")

    all_elements = []
    seen_ids = set()

    for i, (s, w, n, e) in enumerate(tiles):
        logger.info(f"     📦 瓦片 [{i+1}/{len(tiles)}] ({s:.2f},{w:.2f},{n:.2f},{e:.2f})")
        query = f"""
        [out:json][timeout:300][maxsize:1073741824];
        (
          way["building"]({s},{w},{n},{e});
          relation["building"]({s},{w},{n},{e});
        );
        out geom;
        """
        try:
            data = _overpass_request(query)
            if data:
                for el in data.get('elements', []):
                    eid = el.get('id', 0)
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        all_elements.append(el)
                logger.info(f"        ✅ +{len(data.get('elements',[]))} 元素 (累计去重: {len(all_elements)})")
        except Exception as ex:
            logger.warning(f"        ⚠️  瓦片失败: {ex}")

        # 瓦片间间隔
        if i < len(tiles) - 1:
            time.sleep(6)

    if not all_elements:
        logger.error(f"  ❌ 建筑数据获取失败: 所有瓦片均未返回数据")
        return False

    result = {"elements": all_elements}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)

    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    logger.info(f"  📊 总计 {len(all_elements)} 个建筑元素")
    logger.info(f"  ✅ 已保存: {output_file.name} ({size_mb:.1f} MB)")
    return True


# ===========================================================================
#  POI 数据获取
# ===========================================================================
def fetch_pois(city_key: str, output_dir: Path) -> bool:
    """获取指定城市的敏感点和需求点 POI 数据"""
    config = CITY_CONFIG[city_key]
    bbox = config["bbox"]

    # 敏感点: 医院、学校、警察局 -> 禁飞热区
    sensitive_query = f"""
    [out:json][timeout:300][maxsize:1073741824];
    (
      node["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      way["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out center;
    """

    # 需求点: 商业/写字楼/住宅/餐饮/购物 -> 配送起降点高权重
    demand_query = f"""
    [out:json][timeout:300][maxsize:1073741824];
    (
      node["building"~"commercial|office|residential|apartments"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      way["building"~"commercial|office|residential|apartments"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["amenity"~"restaurant|cafe|fast_food|marketplace"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      node["shop"~"supermarket|convenience|mall"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out center;
    """

    queries = {
        "sensitive": sensitive_query,
        "demand": demand_query
    }

    all_ok = True
    for poi_type, query in queries.items():
        output_file = output_dir / f"{city_key}_poi_{poi_type}_raw.json"

        if output_file.exists() and os.path.getsize(output_file) > 100:
            size_kb = os.path.getsize(output_file) / 1024
            logger.info(f"  ✅ {poi_type} POI 已存在: {output_file.name} ({size_kb:.0f} KB)")
            continue

        logger.info(f"  📍 获取 {config['name']} {poi_type} POI...")

        try:
            data = _overpass_request(query)
            if data:
                elements = data.get('elements', [])
                logger.info(f"  📊 获取到 {len(elements)} 个 {poi_type} POI")

                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)

                size_kb = os.path.getsize(output_file) / 1024
                logger.info(f"  ✅ 已保存: {output_file.name} ({size_kb:.0f} KB)")
            else:
                logger.error(f"  ❌ {poi_type} POI 获取失败: 请求返回空")
                all_ok = False

            # Overpass API 限流
            time.sleep(8)

        except Exception as e:
            logger.error(f"  ❌ {poi_type} POI 获取失败: {e}")
            all_ok = False

    return all_ok


# ===========================================================================
#  主入口
# ===========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多城市建筑与POI数据统一获取")
    parser.add_argument("--output", type=str, default="../data/raw",
                        help="原始数据输出目录")
    parser.add_argument("--cities", type=str, default="all",
                        help="要获取的城市, 逗号分隔或'all'. "
                             "可选: " + ", ".join(CITY_CONFIG.keys()))
    parser.add_argument("--skip-existing", action="store_true", default=False,
                        help="跳过已有数据的城市 (现在默认设为不跳过)")
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
    logger.info("🏙️  多城市地理数据统一获取")
    logger.info(f"📁 输出目录: {output_path}")
    logger.info(f"🎯 目标城市: {', '.join(CITY_CONFIG[c]['name'] for c in cities)}")
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

        # 获取建筑
        bld_ok = fetch_buildings(city, output_path)
        # Overpass 限流间隔
        time.sleep(10)

        # 获取 POI
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
