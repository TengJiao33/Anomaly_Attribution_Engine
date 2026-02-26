import os
import argparse
import logging
from pathlib import Path
import json
import requests
import time

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("OSM_POI_Fetcher")

def fetch_pois(output_dir: Path):
    """
    爬取深圳南山区的兴趣点(POI)数据作为低空飞行的敏感点与需求点。
    为避免复杂的依赖问题，统一使用 Overpass API 直接获取 JSON。
    """
    # 深圳南山区周边 Bounding Box
    # (south, west, north, east)
    bbox = (22.48, 113.88, 22.58, 113.98) 
    
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # 获取敏感点 (医院、学校、政府机构) -> 禁飞热区
    sensitive_query = f"""
    [out:json][timeout:250];
    (
      node["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      way["amenity"~"hospital|clinic|school|kindergarten|college|university|police"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out center;
    """
    
    # 获取需求点 (商业写字楼、大型住宅) -> 规划机坪的高权重区
    demand_query = f"""
    [out:json][timeout:250];
    (
      node["building"~"commercial|office|residential|apartments"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      way["building"~"commercial|office|residential|apartments"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out center;
    """
    
    queries = {
        "sensitive": sensitive_query,
        "demand": demand_query
    }
    
    for poi_type, query in queries.items():
        logger.info(f"Fetching {poi_type} POIs from Overpass API...")
        try:
            response = requests.post(overpass_url, data={'data': query})
            response.raise_for_status()
            data = response.json()
            
            elements = data.get('elements', [])
            logger.info(f"Successfully fetched {len(elements)} {poi_type} POIs.")
            
            output_path = output_dir / f"poi_{poi_type}_raw.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
                
            logger.info(f"Saved {poi_type} POIs to: {output_path}")
            
            # Rate limiting sleep
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Failed to fetch {poi_type} POIs: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Urban POI data for No-Fly Zones & Vertiport demands.")
    parser.add_argument("--output", type=str, default="../data/raw", help="Output directory for raw geo data")
    args = parser.parse_args()

    # 确保输出目录存在
    output_path = Path(__file__).resolve().parent / args.output
    output_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"=========== 开始 OSM 敏感与需求兴趣点(POI)采集 ===========")
    
    # 按需检查库
    try:
        import requests
    except ImportError:
        import subprocess, sys
        logger.info("Installing requests...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        
    fetch_pois(output_path)
    
    logger.info("=========== POI 采集任务结束 ===========")
