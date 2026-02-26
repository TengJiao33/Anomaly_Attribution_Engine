import os
import argparse
import logging
from pathlib import Path
import subprocess
import sys

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("OSM_Geo_Fetcher")

def install_requirements():
    """按需自动安装依赖"""
    reqs = ["osmnx", "geopandas", "shapely"]
    logger.info("Checking and installing OSM tools...")
    for lib in reqs:
        try:
            __import__(lib)
        except ImportError:
            logger.info(f"Installing {lib}...")
            # Note: osmnx can be tricky to install via pip alone without conda sometimes, 
            # but we try pip first.
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

def fetch_shenzhen_nanshan_buildings(output_dir: Path):
    """
    爬取深圳南山区的全量 3D 建筑底座
    贯彻“宁滥勿缺”原则，不只抓高新园，抓取整个南山区或更大的 Bounding Box。
    """
    try:
        import osmnx as ox
        import geopandas as gpd
    except ImportError:
        logger.error("Please run script again after dependencies are installed.")
        return

    # 这里我们定义一个稍大的 Bounding Box (南山区及周边)
    # [113.88, 22.48, 113.98, 22.58] 左右
    bbox = (22.58, 22.48, 113.98, 113.88) # North, South, East, West
    
    logger.info(f"Fetching building footprints for Bounding Box: {bbox}")
    try:
        # Since osmnx/shapely C-extensions are causing a "cannot convert float NaN to int"
        # panic on this specific Windows Python environment when parsing OSM relations,
        # we will use the overpass API directly to fetch the raw GeoJSON.
        import requests
        
        # Overpass QL query building
        overpass_url = "http://overpass-api.de/api/interpreter"
        # Bbox in Overpass is (south, west, north, east)
        overpass_query = f"""
        [out:json][timeout:250];
        (
          way["building"]({bbox[1]},{bbox[3]},{bbox[0]},{bbox[2]});
          relation["building"]({bbox[1]},{bbox[3]},{bbox[0]},{bbox[2]});
        );
        out body;
        >;
        out skel qt;
        """
        
        logger.info(f"Sending request to Overpass API...")
        response = requests.post(overpass_url, data={'data': overpass_query})
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Successfully fetched {len(data.get('elements', []))} raw elements from Overpass.")
        
        # Save raw OSM JSON directly (we can process it into strict GeoJSON later if needed)
        raw_output_path = output_dir / "shenzhen_nanshan_buildings_raw.json"
        
        import json
        with open(raw_output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            
        logger.info(f"Building data successfully saved to: {raw_output_path}")
        logger.info(f"File size: {os.path.getsize(raw_output_path) / (1024*1024):.2f} MB")
        
    except Exception as e:
        logger.error(f"Failed to fetch building data: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch large-scale Urban Geo data.")
    parser.add_argument("--output", type=str, default="../data/raw", help="Output directory for raw geo data")
    args = parser.parse_args()

    # 确保输出目录存在
    output_path = Path(__file__).resolve().parent / args.output
    output_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"=========== 开始 OSM 城市基建数据采集 ===========")
    logger.info(f"目标目录: {output_path}")
    logger.info(f"策略: 宁滥勿缺 (Quantity over Quality initially)")

    install_requirements()
    fetch_shenzhen_nanshan_buildings(output_path)
    # TODO: 抓取 POI 的逻辑可以在这里继续添加
    
    logger.info("=========== 采集任务结束 ===========")
