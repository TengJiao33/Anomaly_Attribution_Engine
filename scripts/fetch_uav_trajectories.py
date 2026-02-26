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
logger = logging.getLogger("UAV_Fetcher")

def install_requirements():
    """按需自动安装依赖，包括 tqdm 进度条库"""
    reqs = ["requests", "pandas", "datasets", "tqdm"]
    logger.info("检查并安装必要依赖...")
    for lib in reqs:
        try:
            __import__(lib)
        except ImportError:
            logger.info(f"正在安装 {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

def fetch_huggingface_dataset(output_dir: Path):
    """
    获取 Hugging Face 上的 UAV 轨迹数据集
    源: riotu-lab/Synthetic-UAV-Flight-Trajectories
    遵循"宁滥勿缺"原则，下载全量数据。
    datasets 库自带下载进度条，CSV 写入时使用 tqdm 显示进度。
    """
    try:
        from datasets import load_dataset
        from tqdm import tqdm
        import pandas as pd
    except ImportError:
        logger.error("依赖未就绪，请重新运行脚本。")
        return

    raw_output_path = output_dir / "uav_trajectories_raw.csv"

    # 检查是否已有完整文件（断点续传保护）
    if raw_output_path.exists():
        size_mb = os.path.getsize(raw_output_path) / (1024 * 1024)
        logger.info(f"发现已有文件: {raw_output_path} ({size_mb:.2f} MB)")
        if size_mb > 1.0:
            logger.info("文件看上去已完整，跳过下载。如需重新下载请先删除此文件。")
            return
        else:
            logger.info("文件过小，可能是上次中断的残留，重新下载...")

    logger.info("=" * 60)
    logger.info("正在连接 Hugging Face 下载 UAV 轨迹数据集...")
    logger.info("数据集: riotu-lab/Synthetic-UAV-Flight-Trajectories")
    logger.info("datasets 库将自动显示下载进度条 ↓")
    logger.info("=" * 60)

    try:
        # datasets 库自带下载进度条（tqdm），会自动显示
        dataset = load_dataset(
            "riotu-lab/Synthetic-UAV-Flight-Trajectories",
            split='train'
        )
        total_records = len(dataset)
        logger.info(f"✅ 数据集加载成功！共 {total_records} 条记录")

        # 转换为 DataFrame
        logger.info("正在转换为 DataFrame...")
        df = dataset.to_pandas()
        logger.info(f"DataFrame 列: {list(df.columns)}")
        logger.info(f"DataFrame 形状: {df.shape}")

        # 带进度条写入 CSV
        logger.info(f"正在写入 CSV: {raw_output_path}")
        # 分块写入以显示进度
        chunk_size = 10000
        total_chunks = (len(df) + chunk_size - 1) // chunk_size

        with open(raw_output_path, 'w', newline='', encoding='utf-8') as f:
            for i in tqdm(range(total_chunks), desc="📝 写入CSV", unit="块"):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, len(df))
                chunk = df.iloc[start:end]
                chunk.to_csv(f, index=False, header=(i == 0))

        file_size_mb = os.path.getsize(raw_output_path) / (1024 * 1024)
        logger.info(f"✅ 原始数据已保存: {raw_output_path}")
        logger.info(f"   文件大小: {file_size_mb:.2f} MB")
        logger.info(f"   记录总数: {total_records}")

    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        logger.info("可能原因: 网络不稳定 / 需要代理访问 Hugging Face")
        logger.info("建议: 1) 检查网络连接  2) 设置 HF_ENDPOINT 环境变量使用镜像")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 Hugging Face 获取 UAV 轨迹数据集")
    parser.add_argument("--output", type=str, default="../data/raw",
                        help="原始数据输出目录")
    args = parser.parse_args()

    # 确保输出目录存在
    output_path = Path(__file__).resolve().parent / args.output
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("=========== 开始 UAV 轨迹数据采集 ===========")
    logger.info(f"目标目录: {output_path}")
    logger.info(f"数据来源: Hugging Face (riotu-lab/Synthetic-UAV-Flight-Trajectories)")

    install_requirements()
    fetch_huggingface_dataset(output_path)

    logger.info("=========== 采集任务结束 ===========")
