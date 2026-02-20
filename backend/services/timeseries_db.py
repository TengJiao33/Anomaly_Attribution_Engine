"""
时序数据存储层 (Time-Series Storage Layer)

使用 SQLite 实现轻量级时序数据库，提供：
- market_ticks: 毫秒级行情数据存储
- news_feed: 异构资讯流存储
- 时间窗口查询（真正的"时序对齐"核心能力）
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class TimeSeriesDB:
    """轻量级时序存储引擎，基于 SQLite"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """初始化时序表结构"""
        cursor = self.conn.cursor()
        # 行情 Tick 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL DEFAULT 0,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts 
            ON market_ticks(symbol, timestamp)
        """)

        # 资讯流表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                news_type TEXT DEFAULT 'general',
                sentiment_score REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_symbol_ts 
            ON news_feed(symbol, timestamp)
        """)

        # 案例元信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS case_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                case_date TEXT NOT NULL,
                description TEXT,
                anomaly_type TEXT,
                tick_count INTEGER DEFAULT 0,
                news_count INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    # ---- 写入操作 ---- #

    def insert_ticks(self, ticks: List[Dict]):
        """批量写入行情 Tick 数据"""
        cursor = self.conn.cursor()
        cursor.executemany("""
            INSERT INTO market_ticks (symbol, timestamp, price, open, high, low, close, volume, amount)
            VALUES (:symbol, :timestamp, :price, :open, :high, :low, :close, :volume, :amount)
        """, ticks)
        self.conn.commit()
        return cursor.rowcount

    def insert_news(self, news_items: List[Dict]):
        """批量写入资讯数据"""
        cursor = self.conn.cursor()
        cursor.executemany("""
            INSERT INTO news_feed (symbol, timestamp, source, content, news_type)
            VALUES (:symbol, :timestamp, :source, :content, :news_type)
        """, news_items)
        self.conn.commit()
        return cursor.rowcount

    def set_case_meta(self, symbol: str, symbol_name: str, case_date: str,
                      description: str = "", anomaly_type: str = ""):
        """设置案例元信息"""
        cursor = self.conn.cursor()
        # 统计数据量
        tick_count = cursor.execute(
            "SELECT COUNT(*) FROM market_ticks WHERE symbol=?", (symbol,)
        ).fetchone()[0]
        news_count = cursor.execute(
            "SELECT COUNT(*) FROM news_feed WHERE symbol=?", (symbol,)
        ).fetchone()[0]

        cursor.execute("""
            INSERT OR REPLACE INTO case_meta 
            (symbol, symbol_name, case_date, description, anomaly_type, tick_count, news_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, symbol_name, case_date, description, anomaly_type, tick_count, news_count))
        self.conn.commit()

    # ---- 查询操作 ---- #

    def get_ticks(self, symbol: str, start_ts: Optional[str] = None,
                  end_ts: Optional[str] = None, limit: int = 500) -> List[Dict]:
        """获取指定标的的行情数据，支持时间范围过滤"""
        query = "SELECT * FROM market_ticks WHERE symbol = ?"
        params: list = [symbol]

        if start_ts:
            query += " AND timestamp >= ?"
            params.append(start_ts)
        if end_ts:
            query += " AND timestamp <= ?"
            params.append(end_ts)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        cursor = self.conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_aligned_news(self, symbol: str, anomaly_ts: str,
                         window_before_sec: int = 120,
                         window_after_sec: int = 30) -> List[Dict]:
        """
        核心能力：时间窗口对齐查询。
        获取异动时间点前后的资讯数据（真正的 Time-Window Join）。
        
        :param symbol: 标的代码
        :param anomaly_ts: 异动时间戳 (HH:MM:SS.mmm 或完整 datetime)
        :param window_before_sec: 向前看的秒数（默认2分钟）
        :param window_after_sec: 向后看的秒数（默认30秒）
        """
        query = """
            SELECT * FROM news_feed 
            WHERE symbol = ? 
              AND timestamp >= time(?, '-' || ? || ' seconds')
              AND timestamp <= time(?, '+' || ? || ' seconds')
            ORDER BY timestamp ASC
        """
        cursor = self.conn.cursor()
        rows = cursor.execute(query, (
            symbol, anomaly_ts, str(window_before_sec),
            anomaly_ts, str(window_after_sec)
        )).fetchall()
        return [dict(r) for r in rows]

    def get_all_news_for_symbol(self, symbol: str) -> List[Dict]:
        """获取指定标的的所有资讯"""
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM news_feed WHERE symbol = ? ORDER BY timestamp ASC",
            (symbol,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_case_meta(self) -> Optional[Dict]:
        """获取案例元信息"""
        cursor = self.conn.cursor()
        row = cursor.execute("SELECT * FROM case_meta LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        cursor = self.conn.cursor()
        tick_count = cursor.execute("SELECT COUNT(*) FROM market_ticks").fetchone()[0]
        news_count = cursor.execute("SELECT COUNT(*) FROM news_feed").fetchone()[0]
        symbols = cursor.execute("SELECT DISTINCT symbol FROM market_ticks").fetchall()
        return {
            "tick_count": tick_count,
            "news_count": news_count,
            "symbols": [r[0] for r in symbols]
        }

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
