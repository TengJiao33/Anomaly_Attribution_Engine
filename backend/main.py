import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import asyncio

load_dotenv()

from services.alignment_engine import AlignmentEngineService

app = FastAPI(title="极速归因聚合 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

alignment_service = AlignmentEngineService()

@app.get("/api/alignment_data/{symbol}")
async def get_historical_alignment(symbol: str):
    """
    获取指定标的的初步对齐历史数据快照。
    """
    res = await alignment_service.generate_historical_alignment(symbol)
    return res.model_dump()

@app.websocket("/ws/alignment_feed/{symbol}")
async def websocket_alignment_feed(websocket: WebSocket, symbol: str):
    """
    WebSocket 端点：实时推送高频盘中异动监测与极速归因联合数据流。
    """
    await websocket.accept()
    try:
        async for tick_data in alignment_service.stream_alignment_feed(symbol):
            await websocket.send_json(tick_data)
    except WebSocketDisconnect:
        print(f"Client disconnected from symbol {symbol}")
    except Exception as e:
        print(f"WebSocket Error: {e}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
