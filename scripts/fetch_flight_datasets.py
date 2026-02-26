"""
fetch_flight_datasets.py — 飞行轨迹数据集统一获取脚本

获取以下数据集:
  1. UAV Delivery Dataset (GitHub, 6911条模拟配送轨迹, 20+飞行参数)
  2. AirLab CMU 真实飞行能耗数据 (DJI M100, 195次飞行)
  3. 国家基础学科公共科学数据中心 无人机飞行状态数据 (DJI M300)

输出: data/raw/uav_delivery/, data/raw/airlab_energy/, data/raw/nbsdc_flight/
"""
import os
import sys
import logging
import argparse
import subprocess
import zipfile
import json
import csv
import io
import glob
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("FlightDataFetcher")


def ensure_deps():
    """确保依赖已安装"""
    for lib in ["requests", "tqdm"]:
        try:
            __import__(lib)
        except ImportError:
            logger.info(f"安装 {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])


# ===========================================================================
#  1. UAV Delivery Dataset
# ===========================================================================
def fetch_uav_delivery(output_dir: Path):
    """
    获取 UAV Delivery Dataset — 6911条模拟配送轨迹
    数据来源优先级:
      1. GitHub ZIP 下载 (多个仓库镜像)
      2. Git clone
      3. HuggingFace datasets 搜索
    """
    import requests
    from tqdm import tqdm

    dest = output_dir / "uav_delivery"
    dest.mkdir(parents=True, exist_ok=True)

    marker = dest / "_download_complete"
    if marker.exists():
        logger.info(f"✅ UAV Delivery Dataset 已存在, 跳过下载 ({dest})")
        return True

    # 方法1: 尝试从 GitHub 下载 zip 压缩包
    urls = [
        "https://github.com/saimouafaiz/UAV-Delievery/archive/refs/heads/main.zip",
        "https://github.com/OreateAI/UAV-Delivery/archive/refs/heads/main.zip",
        "https://github.com/YassineBenAbdelworked/UAV-Delievery/archive/refs/heads/main.zip",
        "https://github.com/elkinvg/UAV-Delievery/archive/refs/heads/main.zip",
        "https://github.com/qz701731tby/UAV-Delievery/archive/refs/heads/main.zip",
    ]

    zip_path = dest / "download.zip"
    downloaded = False

    for url in urls:
        logger.info(f"尝试下载: {url}")
        try:
            resp = requests.get(url, stream=True, timeout=30, 
                              allow_redirects=True)
            if resp.status_code == 200:
                total = int(resp.headers.get('content-length', 0))
                with open(zip_path, 'wb') as f:
                    with tqdm(total=total, unit='B', unit_scale=True,
                              desc="📥 UAV Delivery") as pbar:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))
                downloaded = True
                break
            else:
                logger.warning(f"  HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"  失败: {e}")

    # 方法2: Git clone
    if not downloaded:
        logger.info("ZIP下载失败, 尝试 git clone...")
        clone_urls = [
            "https://github.com/saimouafaiz/UAV-Delievery.git",
            "https://github.com/OreateAI/UAV-Delivery.git",
            "https://github.com/elkinvg/UAV-Delievery.git",
        ]
        for clone_url in clone_urls:
            try:
                clone_dest = dest / "repo"
                if clone_dest.exists():
                    import shutil
                    shutil.rmtree(clone_dest)
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, str(clone_dest)],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    downloaded = True
                    logger.info(f"✅ Git clone 成功")
                    break
            except Exception as e:
                logger.warning(f"  clone 失败: {e}")

    # 方法3: 通过 HuggingFace datasets 库搜索同名数据集
    if not downloaded:
        logger.info("GitHub 不可用, 尝试 HuggingFace...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", 
                                   "datasets", "-q"], timeout=60)
            from datasets import load_dataset
            # 尝试加载可能存在的 HuggingFace 镜像
            hf_names = [
                "saimouafaiz/UAV-Delivery",
                "riotu-lab/UAV-Delivery-Dataset",
            ]
            for hf_name in hf_names:
                try:
                    ds = load_dataset(hf_name, split='train')
                    df = ds.to_pandas()
                    csv_path = dest / "uav_delivery_data.csv"
                    df.to_csv(csv_path, index=False)
                    downloaded = True
                    logger.info(f"✅ HuggingFace 下载成功: {len(df)} 条记录")
                    break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"  HuggingFace 也失败: {e}")

    if not downloaded:
        logger.error("❌ UAV Delivery Dataset 所有下载方式均失败")
        logger.info("📋 请手动搜索下载: https://github.com/search?q=UAV-Delievery+dataset")
        logger.info("   或从论文 'Delivery with UAVs: a simulated dataset via ATS' 获取")
        return False

    # 解压 ZIP
    if zip_path.exists():
        logger.info("正在解压...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(dest)
            os.remove(zip_path)
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return False

    marker.write_text("done")
    log_files = list(dest.rglob("*.log")) + list(dest.rglob("*.csv"))
    logger.info(f"📊 UAV Delivery Dataset: 共找到 {len(log_files)} 个数据文件")
    return True


# ===========================================================================
#  2. AirLab CMU 真实飞行能耗数据
# ===========================================================================
def fetch_airlab_energy(output_dir: Path):
    """
    获取 AirLab CMU 无人机包裹配送飞行能耗数据集
    DJI Matrice 100, 209次飞行, 含位置和能耗数据
    数据来源: Figshare (doi:10.1184/R1/12683453)
    """
    import requests
    from tqdm import tqdm

    dest = output_dir / "airlab_energy"
    dest.mkdir(parents=True, exist_ok=True)

    marker = dest / "_download_complete"
    if marker.exists():
        logger.info(f"✅ AirLab 能耗数据已存在, 跳过下载 ({dest})")
        return True

    # 直接使用 Figshare 文件下载链接 (不经过 API)
    # 这些链接可以从 https://figshare.com/articles/dataset/12683453 页面获取
    logger.info("正在尝试从 Figshare 下载 AirLab 数据集...")

    # 尝试 Figshare API 获取实际文件URL
    api_url = "https://api.figshare.com/v2/articles/12683453"
    files_to_download = []

    try:
        resp = requests.get(api_url, timeout=30)
        if resp.status_code == 200:
            try:
                article = resp.json()
                files_to_download = [
                    (f["name"], f["download_url"], f.get("size", 0))
                    for f in article.get("files", [])
                ]
                logger.info(f"  从 Figshare API 获取到 {len(files_to_download)} 个文件")
            except Exception:
                logger.warning("  Figshare API 响应解析失败")
    except Exception as e:
        logger.warning(f"  Figshare API 不可达: {e}")

    # 如果 API 失败，使用手动备用链接
    if not files_to_download:
        logger.info("  使用备用直接下载链接...")
        files_to_download = [
            ("flight_data.zip", 
             "https://ndownloader.figshare.com/files/23585474", 0),
        ]

    downloaded_count = 0
    for fname, furl, fsize in files_to_download:
        fpath = dest / fname
        if fpath.exists() and os.path.getsize(fpath) > 1000:
            logger.info(f"  跳过已存在: {fname}")
            downloaded_count += 1
            continue

        logger.info(f"  下载: {fname}")
        try:
            dl_resp = requests.get(furl, stream=True, timeout=120, 
                                   allow_redirects=True)
            dl_resp.raise_for_status()
            actual_size = int(dl_resp.headers.get('content-length', fsize))

            with open(fpath, 'wb') as f:
                with tqdm(total=actual_size, unit='B', unit_scale=True,
                          desc=f"📥 {fname}") as pbar:
                    for chunk in dl_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))

            file_size = os.path.getsize(fpath)
            logger.info(f"  ✅ 已下载: {fname} ({file_size/(1024*1024):.1f} MB)")
            downloaded_count += 1
        except Exception as e:
            logger.error(f"  ❌ 下载失败 {fname}: {e}")

    # 解压 ZIP 文件
    for zfile in dest.glob("*.zip"):
        if os.path.getsize(zfile) > 1000:  # 确保不是空文件
            logger.info(f"  解压: {zfile.name}")
            try:
                with zipfile.ZipFile(zfile, 'r') as zf:
                    zf.extractall(dest)
                logger.info("  ✅ 解压完成")
            except Exception as e:
                logger.warning(f"  解压失败: {e}")

    if downloaded_count > 0:
        marker.write_text("done")
        logger.info("✅ AirLab 能耗数据下载完成")
        return True
    else:
        logger.error("❌ AirLab 数据全部下载失败")
        logger.info("备用方案: 请手动访问 https://figshare.com/articles/dataset/12683453")
        return False


# ===========================================================================
#  3. 国家基础学科公共科学数据中心 无人机飞行状态数据
# ===========================================================================
def fetch_nbsdc_flight(output_dir: Path):
    """
    获取国家基础学科公共科学数据中心的无人机飞行状态数据
    DJI M300, 含位置/姿态/速度/IMU/RTK 数据, ~150MB
    数据来源: nbsdc.cn
    注意: 该数据集可能需要注册登录后下载, 此处尝试直接获取
    """
    import requests

    dest = output_dir / "nbsdc_flight"
    dest.mkdir(parents=True, exist_ok=True)

    marker = dest / "_download_complete"
    if marker.exists():
        logger.info(f"✅ 国家数据中心飞行数据已存在, 跳过 ({dest})")
        return True

    # 该数据集通常在 nbsdc.cn 平台上，可能需要手动下载
    # 我们尝试几个可能的直接下载链接
    logger.info("正在尝试获取国家数据中心无人机飞行状态数据...")

    # 尝试搜索已知的公开镜像或直接链接
    possible_urls = [
        "https://www.nbsdc.cn/dataSet/handle/1",  # 示例
    ]

    # 由于该数据集通常需要登录下载，我们创建一个说明文件
    readme_path = dest / "README_下载指南.md"
    readme_content = """# 国家基础学科公共科学数据中心 - 无人机飞行状态数据

## 数据简介
- **数据源**: DJI M300 无人机飞控数据
- **采集方式**: ROS 订阅话题获取飞控数据
- **内容**: 位置、姿态、飞行速度、角速度、原始IMU和RTK数据
- **数据量**: 约150MB

## 下载方式
1. 访问 https://www.nbsdc.cn
2. 搜索 "无人机飞行状态数据"
3. 注册/登录后下载
4. 将下载的文件放在此目录下

## 数据格式
数据通过ROS bag文件或CSV导出，包含以下字段:
- timestamp: 时间戳
- position_x/y/z: 位置坐标
- orientation_roll/pitch/yaw: 姿态角
- velocity_x/y/z: 飞行速度
- angular_velocity_x/y/z: 角速度
- imu_accel_x/y/z: IMU加速度
- imu_gyro_x/y/z: IMU陀螺仪
- rtk_lat/lon/alt: RTK差分定位
"""
    readme_path.write_text(readme_content, encoding='utf-8')
    logger.info(f"📝 已生成下载指南: {readme_path}")
    logger.warning("⚠️  该数据集可能需要手动登录 nbsdc.cn 下载")
    logger.info("   也可以跳过此数据集，现有数据足以支撑项目")

    # 尝试直接下载（可能会失败）
    try:
        resp = requests.get(
            "https://www.nbsdc.cn/api/data/download",
            params={"keyword": "无人机飞行状态"},
            timeout=15
        )
        if resp.status_code == 200 and len(resp.content) > 1000:
            data_path = dest / "flight_data.zip"
            data_path.write_bytes(resp.content)
            logger.info(f"✅ 成功下载: {data_path}")
            marker.write_text("done")
            return True
    except Exception:
        pass

    logger.info("ℹ️  已创建下载指南，请手动下载后放入目录")
    return False


# ===========================================================================
#  主入口
# ===========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="飞行轨迹数据集统一获取")
    parser.add_argument("--output", type=str, default="../data/raw",
                        help="原始数据输出目录")
    parser.add_argument("--skip-uav-delivery", action="store_true",
                        help="跳过 UAV Delivery Dataset")
    parser.add_argument("--skip-airlab", action="store_true",
                        help="跳过 AirLab 能耗数据")
    parser.add_argument("--skip-nbsdc", action="store_true",
                        help="跳过国家数据中心飞行数据")
    args = parser.parse_args()

    output_path = Path(__file__).resolve().parent / args.output
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("🚁 飞行轨迹数据集统一获取")
    logger.info(f"📁 输出目录: {output_path}")
    logger.info("=" * 60)

    ensure_deps()

    results = {}

    if not args.skip_uav_delivery:
        results["UAV Delivery"] = fetch_uav_delivery(output_path)

    if not args.skip_airlab:
        results["AirLab Energy"] = fetch_airlab_energy(output_path)

    if not args.skip_nbsdc:
        results["NBSDC Flight"] = fetch_nbsdc_flight(output_path)

    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 下载结果汇总:")
    for name, ok in results.items():
        status = "✅ 成功" if ok else "⚠️  需手动处理"
        logger.info(f"  {name}: {status}")
    logger.info("=" * 60)
