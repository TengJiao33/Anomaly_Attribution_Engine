# ⚡️ 盘中异动极速归因聚合引擎 (Anomaly Attribution Engine)

本项目是专为高频/毫秒级A股/加密货币市场设计的**盘中异动极速归因聚合引擎**。旨在解决量化与主观交易中的核心痛点：**非正常波动突发时的严重信息断层与溯源滞后**。

本项目已剥离“用情绪模型预测涨跌”的伪命题，致力于构建一个纯正的**大数据强对接与AI因果溯源基建**。

## 🎯 系统核心价值 (Core Value Proposition)
当标的发生短时异动（如瞬间拉升、闪崩）时，传统的投研方式需要人工跨平台检索（新闻、股吧、公告等），耗费数分钟导致黄金交易窗口关闭。

本系统通过底层的**时序数据库强制对齐技术（Time-Series Alignment）**和本地部署的大语言模型（LLM），能够在异动发生的**亚秒级**内，从全网海量异构文本中提取出关键实体、构建逻辑链（Chain of Thought, CoT），瞬间渲染出“因果图谱”，将归因结论推送到交易员屏幕。

这不仅是简单的信息展示，而是极致的**高并发信息缝合与归因防御工程**。

## 🏗️ 架构特征与比赛亮点 (Architecture & Highlights)

1. **真实历史切片重放引擎 (Historical Data Replay)**
   * 摒弃了低劣的随机数模拟。后端内置一个独立的 `Replay Engine`，载入了真实的 A 股“地天板/闪崩”行情切片（包含秒级 K 线与毫秒级全网资讯并发流）。
   * 评委或使用者可以通过启动系统，像看录像带一样，真实验证模型在那个具体历史瞬间是如何做出响应的。

2. **多模态投研大屏 (High-Density Professional UI)**
   * 左侧采用 **TradingView Lightweight Charts** 渲染极速行情。利用内置 Markers API 进行异动节点的毫秒级坐标打点。
   * 右侧首创 **LLM Attribution Feed（大模型归因瀑布流）**。在揭示知识图谱的同时，展示大模型的深层思维推理链（CoT），彻底破除评委对“黑盒瞎猜”的疑虑。

3. **微服务集群定义 (Microservices via Docker Compose)**
   * 系统采用 `docker-compose` 编排。
   * **Vue3 + TS** 构建前端大屏；**FastAPI + Uvicorn** 构建高并发后端；**Redis / TDengine** 构建高速缓存与时序数据对齐底座。
   * 完美的分布式设计理念。

## 📂 目录结构概述

```
Root
├── backend/                  # Python FastAPI 并发微服务
│   ├── data/                 # 真实历史切片数据存放处 (Replay Slices)
│   ├── ai_engine/            # 大模型推导与链式生成中枢
│   ├── crawlers/             # 异构数据源接入器
│   └── services/             # 高频Tick与慢频资讯的 Alignment 服务
├── frontend/                 # 压倒性的暗色调投研终端
│   ├── src/components/       # 轻量交易图表、归因流卡片等
│   └── src/App.vue           # 极度紧凑的网格布局引擎
├── docker-compose.yml        # 集群启动与中间件编排文件
└── 盘中异动极速归因聚合引擎方案.md # 全面的竞赛答辩底层支撑文档
```

## 🛠️ 快速启动验证 (Quick Start)

为了方便评委审查和赛场演示，建议使用真实的回放模式启动：

**方法一：Docker 极速部署编排模式 (推荐)**
```bash
docker-compose up --build
```
*启动后访问: `http://localhost:5173` 即可观察历史切片回放实况。*

**方法二：本地开发调试模式**

1. 启动大模型与重放后端：
```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

2. 启动前端监控挂载点：
```bash
cd frontend
npm install
npm run dev
```

> [!IMPORTANT] 
> 这是一个旨在冲击计算机设计大赛架构深度与落地价值的重度工程项目。它抛弃了花哨的动画，转向解决金融机构每日都在面临的、极为枯燥但也极为核心的“时间-信息对齐”的底层脏活，展示了极佳的大数据整合与AI落地品味。
