"""
盘中异动极速归因聚合引擎 API
FastAPI 高并发后端入口
"""

import os
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger
import sys
import asyncio

load_dotenv()

# 配置 loguru 日志
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")

from services.alignment_engine import AlignmentEngineService
from services.live_feed_generator import LiveFeedGenerator

app = FastAPI(
    title="盘中异动极速归因聚合 API",
    version="4.0.0",
    description="高频盘中异动检测与实时 LLM 归因系统 — 多信号贝叶斯融合架构",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

alignment_service = AlignmentEngineService()


# ===== REST API ===== #

@app.get("/api/available_cases")
async def get_available_cases():
    """获取所有可用的回放案例列表"""
    cases = alignment_service.get_available_cases()
    return [c.model_dump() for c in cases]


@app.get("/api/alignment_data/{case_id}")
async def get_historical_alignment(case_id: str):
    """获取指定案例的初始对齐历史数据快照"""
    res = await alignment_service.generate_historical_alignment(case_id)
    return res.model_dump()


@app.get("/api/system_status")
async def get_system_status():
    """获取系统运行状态指标（供前端 Footer 使用）"""
    return alignment_service.get_system_metrics()


@app.get("/api/system_events")
async def get_system_events():
    """获取系统事件日志（供前端 TickerTape 使用）"""
    return alignment_service.get_system_events()


# ===== WebSocket ===== #

@app.websocket("/ws/alignment_feed/{case_id}")
async def websocket_alignment_feed(websocket: WebSocket, case_id: str):
    """
    WebSocket 端点：实时推送高频盘中异动监测与极速归因联合数据流。
    支持双向通信：
    - 服务端 → 客户端: tick 数据流
    - 客户端 → 服务端: 回放控制指令 (pause/resume/set_speed)
    """
    await websocket.accept()
    logger.info(f"WebSocket 连接建立: {case_id}")

    # 回放控制状态（与此连接绑定）
    control_state = {
        "paused": False,
        "speed": 1.0,
    }

    # 启动回放数据流
    feed_task = asyncio.create_task(
        _stream_with_control(websocket, case_id, control_state)
    )

    try:
        # 持续监听客户端控制消息
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(raw)
                action = msg.get("action", "")

                if action == "pause":
                    control_state["paused"] = True
                    logger.info(f"[{case_id}] 回放暂停")
                elif action == "resume":
                    control_state["paused"] = False
                    logger.info(f"[{case_id}] 回放继续")
                elif action == "set_speed":
                    speed = float(msg.get("value", 1.0))
                    control_state["speed"] = max(0.1, min(speed, 10.0))
                    logger.info(f"[{case_id}] 回放速度: {control_state['speed']}x")
            except asyncio.TimeoutError:
                # 没有控制消息，继续循环
                if feed_task.done():
                    break
                continue
    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {case_id}")
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
    finally:
        feed_task.cancel()


@app.websocket("/ws/live_feed")
async def websocket_live_feed(websocket: WebSocket):
    """
    真·实盘推演端点：
    推送来自造浪机的无限流高频 Tick 数据。
    """
    await websocket.accept()
    logger.info("WebSocket 实盘监听已接入 (Live Mode)")
    
    generator = LiveFeedGenerator(symbol="000001.SZ", base_price=10.50)
    
    # 将实盘流推给前端
    stream_task = asyncio.create_task(_stream_live_feed(websocket, generator))
    
    try:
        # 维持长连接
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("实盘 WebSocket 断开")
    except Exception as e:
        logger.error(f"实盘流异常: {e}")
    finally:
        stream_task.cancel()


async def _stream_live_feed(websocket: WebSocket, generator: LiveFeedGenerator):
    """推送独立生成的造浪机实盘数据包"""
    try:
        async for tick_data in generator.stream(alignment_service):
            await websocket.send_json(tick_data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"实盘下发异常: {e}")


async def _stream_with_control(
    websocket: WebSocket, case_id: str, control: dict
):
    """带回放控制的数据流推送"""
    try:
        async for tick_data in alignment_service.stream_alignment_feed(
            case_id, control_state=control
        ):
            await websocket.send_json(tick_data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"流式推送异常: {e}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
