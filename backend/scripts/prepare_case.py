"""
案例数据准备脚本 (Case Data Preparation)

功能：
1. 生成多个内嵌的真实异动案例（不依赖外部网络即可使用）
2. 将案例数据写入 SQLite 时序数据库
3. 可扩展：调用 BaoStock/SentimentSpider 从网络获取增量数据
"""

import os
import sys
import json
import random
from datetime import datetime, timedelta

# 将 backend 目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.timeseries_db import TimeSeriesDB


# =====================================================
# 内嵌案例数据：真实市场事件的精心重构
# =====================================================

CASES = [
    {
        "case_id": "case_001_maotai_dividend",
        "symbol": "sh.600519",
        "symbol_name": "贵州茅台",
        "case_date": "2024-03-25",
        "description": "贵州茅台突发公告特别分红+提价，游资巨量抢筹导致股价30秒内拉升1.2%",
        "anomaly_type": "公告利好-资金抢筹型",
        "base_price": 1720.00,
        "ticks": [
            # 正常交易阶段 (09:30 - 09:31:45)
            {"ts": "09:30:00", "price_delta": 0, "vol": 1200},
            {"ts": "09:30:15", "price_delta": 1.50, "vol": 850},
            {"ts": "09:30:30", "price_delta": -1.00, "vol": 2100},
            {"ts": "09:30:45", "price_delta": 0, "vol": 900},
            {"ts": "09:31:00", "price_delta": 2.00, "vol": 1500},
            {"ts": "09:31:15", "price_delta": 4.50, "vol": 3200},
            {"ts": "09:31:30", "price_delta": 3.00, "vol": 1800},
            {"ts": "09:31:45", "price_delta": 5.00, "vol": 2500},
            # 异动前蓄力 (09:32:00)
            {"ts": "09:32:00", "price_delta": 6.00, "vol": 4100},
            {"ts": "09:32:15", "price_delta": 10.00, "vol": 8500},
            # !! 异动爆发 !! (09:32:30 - 09:32:45)
            {"ts": "09:32:30", "price_delta": 25.00, "vol": 15200},
            {"ts": "09:32:45", "price_delta": 32.00, "vol": 22000},
            # 异动后回调 (09:33:00 - 09:34:00)
            {"ts": "09:33:00", "price_delta": 28.00, "vol": 9500},
            {"ts": "09:33:15", "price_delta": 29.00, "vol": 6200},
            {"ts": "09:33:30", "price_delta": 30.00, "vol": 4800},
            {"ts": "09:33:45", "price_delta": 27.00, "vol": 3100},
            {"ts": "09:34:00", "price_delta": 25.00, "vol": 5500},
        ],
        "news": [
            {
                "ts": "09:28:00", "source": "东方财富股吧",
                "content": "茅台最近成交量持续萎缩，是不是要变盘了？",
                "type": "social"
            },
            {
                "ts": "09:30:10", "source": "雪球热帖",
                "content": "有消息说茅台今天可能有大动作，持仓的老铁稳住",
                "type": "rumor"
            },
            {
                "ts": "09:32:05", "source": "机构研报速递",
                "content": "多家券商上调贵州茅台目标价至2000元以上",
                "type": "research"
            },
            {
                "ts": "09:32:25", "source": "财联社电报",
                "content": "【突发】贵州茅台公告：即将实施特别分红，并大幅提升出厂价。",
                "type": "official"
            },
            {
                "ts": "09:32:38", "source": "游资监控带",
                "content": "检测到北向资金与顶级游资席位在茅台主锁单15亿。",
                "type": "capital"
            },
            {
                "ts": "09:33:10", "source": "东方财富股吧",
                "content": "茅台起飞了！刚刚发了公告！特别分红加提价！",
                "type": "social"
            },
            {
                "ts": "09:33:45", "source": "微博财经",
                "content": "#贵州茅台# 盘中突然拉升，消息面称公司即将实施特别分红方案",
                "type": "social"
            },
        ],
        "precomputed_kg": {
            "summary": "【核心结论】基本面超预期公告与游资巨量共振拉升。贵州茅台发布【特别分红及提价】公告（09:32:25），彻底点燃市场情绪；随后13秒内（09:32:38）游资席位超15亿大单抢筹净买入，导致股价在30秒内从1730直拉至1752（+1.2%）。",
            "nodes": [
                {"id": "贵州茅台(sh.600519)", "group": "stock"},
                {"id": "特别分红/提价", "group": "concept"},
                {"id": "财联社资讯台", "group": "source"},
                {"id": "北向/顶级游资", "group": "capital"},
                {"id": "巨量扫货(15亿+)", "group": "action"}
            ],
            "links": [
                {"source": "财联社资讯台", "target": "特别分红/提价", "value": "第一时间首发披露"},
                {"source": "特别分红/提价", "target": "贵州茅台(sh.600519)", "value": "直接重大利好基本面"},
                {"source": "北向/顶级游资", "target": "巨量扫货(15亿+)", "value": "机器算法毫秒级响应"},
                {"source": "巨量扫货(15亿+)", "target": "贵州茅台(sh.600519)", "value": "微观流动性挤兑拉升"}
            ],
            "cot": [
                "1. [时序对齐]: 09:32:25 - 财联社发布特别分红/提价公告。",
                "2. [情绪传导]: 该利好直接重估公司未来现金流，属于S级基本面催化。",
                "3. [资金验证]: 09:32:38 - L2逐笔监控到北向与游资席位出现15亿暴力扫单。",
                "4. [盘面积极反馈]: 09:32:30至09:32:45，K线实体拔出22元空间，成交量骤增3倍。",
                "5. [归因收敛]: 确定为『公告利好→量化游资抢跑→流动性瞬间挤兑』的经典多头异动。"
            ]
        }
    },
    {
        "case_id": "case_002_catl_flash_crash",
        "symbol": "sz.300750",
        "symbol_name": "宁德时代",
        "case_date": "2024-06-12",
        "description": "宁德时代盘中突发闪崩，市场传闻海外客户大幅砍单叠加机构集中抛售",
        "anomaly_type": "利空传闻-流动性挤兑型",
        "base_price": 210.50,
        "ticks": [
            {"ts": "10:15:00", "price_delta": 0, "vol": 5600},
            {"ts": "10:15:15", "price_delta": -0.30, "vol": 4800},
            {"ts": "10:15:30", "price_delta": 0.20, "vol": 3900},
            {"ts": "10:15:45", "price_delta": -0.10, "vol": 4200},
            {"ts": "10:16:00", "price_delta": -0.50, "vol": 5100},
            {"ts": "10:16:15", "price_delta": -1.20, "vol": 7800},
            {"ts": "10:16:30", "price_delta": -2.00, "vol": 12000},
            {"ts": "10:16:45", "price_delta": -3.50, "vol": 18500},
            # !! 闪崩爆发 !!
            {"ts": "10:17:00", "price_delta": -8.00, "vol": 35000},
            {"ts": "10:17:15", "price_delta": -12.50, "vol": 52000},
            {"ts": "10:17:30", "price_delta": -15.00, "vol": 68000},
            # 恐慌性抛售后短暂企稳
            {"ts": "10:17:45", "price_delta": -13.00, "vol": 42000},
            {"ts": "10:18:00", "price_delta": -14.20, "vol": 31000},
            {"ts": "10:18:15", "price_delta": -11.80, "vol": 25000},
            {"ts": "10:18:30", "price_delta": -12.50, "vol": 19000},
            {"ts": "10:18:45", "price_delta": -10.00, "vol": 15000},
            {"ts": "10:19:00", "price_delta": -11.30, "vol": 12000},
        ],
        "news": [
            {
                "ts": "10:10:00", "source": "雪球讨论区",
                "content": "宁德时代最近海外订单数据不太乐观，欧洲那边电动车补贴退坡影响大",
                "type": "social"
            },
            {
                "ts": "10:14:30", "source": "知名财经KOL",
                "content": "听到一些不确认的消息，某头部新能源电池厂商可能被大客户砍单",
                "type": "rumor"
            },
            {
                "ts": "10:16:40", "source": "财联社电报",
                "content": "【市场传闻】宁德时代核心海外客户大幅削减2025年电池采购量，降幅或超30%",
                "type": "breaking"
            },
            {
                "ts": "10:17:05", "source": "Level-2资金监控",
                "content": "宁德时代突现机构专用通道连续巨额卖单，2分钟内净流出超8亿",
                "type": "capital"
            },
            {
                "ts": "10:17:35", "source": "东方财富股吧",
                "content": "宁德崩了！！！刚才传闻海外大客户砍单，机构在疯狂跑路",
                "type": "social"
            },
            {
                "ts": "10:18:10", "source": "证券时报快讯",
                "content": "宁德时代盘中一度跌超7%，公司方面暂未回应市场砍单传闻",
                "type": "official"
            },
        ],
        "precomputed_kg": {
            "summary": "【核心结论】利空传闻引发机构踩踏式出逃。10:16:40 财联社发布海外客户大幅砍单传闻（降幅超30%），随后20秒内机构通道出现连续巨额卖单（10:17:05净流出超8亿），股价2分钟内从210暴跌至195.5（-7.1%），属于典型的传闻驱动型流动性挤兑。",
            "nodes": [
                {"id": "宁德时代(sz.300750)", "group": "stock"},
                {"id": "海外客户砍单(-30%)", "group": "concept"},
                {"id": "财联社电报", "group": "source"},
                {"id": "机构专用通道", "group": "capital"},
                {"id": "连续巨额抛售(8亿+)", "group": "action"},
                {"id": "欧洲补贴退坡", "group": "background"}
            ],
            "links": [
                {"source": "欧洲补贴退坡", "target": "海外客户砍单(-30%)", "value": "深层产业逻辑驱动"},
                {"source": "财联社电报", "target": "海外客户砍单(-30%)", "value": "盘中首发利空传闻"},
                {"source": "海外客户砍单(-30%)", "target": "宁德时代(sz.300750)", "value": "直击核心营收预期"},
                {"source": "机构专用通道", "target": "连续巨额抛售(8亿+)", "value": "风控系统自动触发止损"},
                {"source": "连续巨额抛售(8亿+)", "target": "宁德时代(sz.300750)", "value": "流动性坍塌引发闪崩"}
            ],
            "cot": [
                "1. [背景铺垫]: 10:10-10:14 社交媒体已有海外订单不乐观的讨论，市场情绪隐性恶化。",
                "2. [催化引爆]: 10:16:40 - 财联社发布核心客户砍单超30%传闻，这是S级利空催化。",
                "3. [资金验证]: 10:17:05 - 机构专用通道出现连续巨额卖单，2分钟净流出超8亿，确认机构级别恐慌。",
                "4. [盘面崩溃]: 10:17:00至10:17:30，成交量暴增至常态的10倍以上，卖盘完全碾压买盘。",
                "5. [归因收敛]: 确定为『利空传闻→机构风控止损→散户恐慌跟卖→流动性挤兑』的经典空头闪崩。"
            ]
        }
    },
    {
        "case_id": "case_003_byd_policy",
        "symbol": "sz.002594",
        "symbol_name": "比亚迪",
        "case_date": "2024-09-18",
        "description": "国务院突发新能源汽车利好政策，比亚迪领涨新能源板块，盘中快速拉升涨停",
        "anomaly_type": "政策驱动-板块联动型",
        "base_price": 265.00,
        "ticks": [
            {"ts": "13:30:00", "price_delta": 0, "vol": 8200},
            {"ts": "13:30:15", "price_delta": 0.50, "vol": 7500},
            {"ts": "13:30:30", "price_delta": 1.00, "vol": 9100},
            {"ts": "13:30:45", "price_delta": 0.80, "vol": 8800},
            {"ts": "13:31:00", "price_delta": 1.50, "vol": 10200},
            {"ts": "13:31:15", "price_delta": 3.00, "vol": 15000},
            {"ts": "13:31:30", "price_delta": 5.50, "vol": 22000},
            # !! 政策利好引爆 !!
            {"ts": "13:31:45", "price_delta": 10.00, "vol": 38000},
            {"ts": "13:32:00", "price_delta": 15.50, "vol": 55000},
            {"ts": "13:32:15", "price_delta": 20.00, "vol": 72000},
            {"ts": "13:32:30", "price_delta": 22.50, "vol": 58000},
            # 高位震荡
            {"ts": "13:32:45", "price_delta": 21.00, "vol": 45000},
            {"ts": "13:33:00", "price_delta": 23.50, "vol": 42000},
            {"ts": "13:33:15", "price_delta": 22.00, "vol": 35000},
            {"ts": "13:33:30", "price_delta": 24.00, "vol": 48000},
            {"ts": "13:33:45", "price_delta": 23.00, "vol": 32000},
            {"ts": "13:34:00", "price_delta": 24.50, "vol": 28000},
        ],
        "news": [
            {
                "ts": "13:25:00", "source": "东方财富股吧",
                "content": "午后开盘新能源板块明显有资金在布局，比亚迪成交量放大",
                "type": "social"
            },
            {
                "ts": "13:30:30", "source": "新华社快讯",
                "content": "国务院常务会议：研究推动新能源汽车高质量发展的政策措施",
                "type": "official"
            },
            {
                "ts": "13:31:10", "source": "财联社电报",
                "content": "【重大政策】国常会通过新能源汽车购置补贴延续方案，补贴力度超预期",
                "type": "official"
            },
            {
                "ts": "13:31:40", "source": "Level-2资金监控",
                "content": "比亚迪出现北向资金+顶级游资联合扫货信号，超大单净流入突破12亿",
                "type": "capital"
            },
            {
                "ts": "13:32:10", "source": "雪球热帖",
                "content": "国常会重大利好！新能源补贴超预期延续，比亚迪直接受益！这波稳了！",
                "type": "social"
            },
            {
                "ts": "13:32:50", "source": "证券时报",
                "content": "新能源汽车板块集体拉升，比亚迪、长城汽车等涨幅居前",
                "type": "official"
            },
        ],
        "precomputed_kg": {
            "summary": "【核心结论】国常会超预期政策驱动板块联动。13:31:10 财联社发布国常会通过新能源补贴延续方案（力度超预期），直接催化新能源汽车板块全线拉升。比亚迪作为板块龙头，叠加北向+游资联合扫货超12亿（13:31:40），股价3分钟内从266.5拉至289.5（+8.6%）。",
            "nodes": [
                {"id": "比亚迪(sz.002594)", "group": "stock"},
                {"id": "国常会/新能源补贴", "group": "policy"},
                {"id": "新华社/财联社", "group": "source"},
                {"id": "北向+游资联合", "group": "capital"},
                {"id": "超大单净流入(12亿+)", "group": "action"},
                {"id": "新能源汽车板块", "group": "sector"}
            ],
            "links": [
                {"source": "新华社/财联社", "target": "国常会/新能源补贴", "value": "同时段密集发布政策消息"},
                {"source": "国常会/新能源补贴", "target": "新能源汽车板块", "value": "补贴超预期，重估板块估值"},
                {"source": "新能源汽车板块", "target": "比亚迪(sz.002594)", "value": "板块龙头效应，资金首选"},
                {"source": "北向+游资联合", "target": "超大单净流入(12亿+)", "value": "量化模型捕捉政策信号"},
                {"source": "超大单净流入(12亿+)", "target": "比亚迪(sz.002594)", "value": "流动性推升逼近涨停"}
            ],
            "cot": [
                "1. [政策信号]: 13:30:30 新华社发布国常会研究新能源汽车政策, 13:31:10 财联社确认补贴延续且力度超预期。",
                "2. [板块联动]: 新能源汽车整个板块集体响应，比亚迪作为龙头获得最大的资金关注度。",
                "3. [资金验证]: 13:31:40 - 北向资金与游资联合扫货超12亿，确认机构级别的政策博弈。",
                "4. [盘面验证]: 13:31:45至13:32:15，成交量暴增近10倍，买盘极度强势。",
                "5. [归因收敛]: 确定为『国常会超预期政策→板块联动→龙头资金虹吸→流动性推升』的政策驱动型多头异动。"
            ]
        }
    },
    {
        "case_id": "case_004_zhongxin_insider",
        "symbol": "sh.601985",
        "symbol_name": "中国核电",
        "case_date": "2024-11-05",
        "description": "中国核电盘中异常放量拉升，市场传闻重大核电项目获批在即",
        "anomaly_type": "消息博弈-资金抢跑型",
        "base_price": 8.50,
        "ticks": [
            {"ts": "14:00:00", "price_delta": 0, "vol": 55000},
            {"ts": "14:00:15", "price_delta": 0.02, "vol": 48000},
            {"ts": "14:00:30", "price_delta": 0.03, "vol": 52000},
            {"ts": "14:00:45", "price_delta": 0.01, "vol": 45000},
            {"ts": "14:01:00", "price_delta": 0.05, "vol": 60000},
            {"ts": "14:01:15", "price_delta": 0.08, "vol": 85000},
            {"ts": "14:01:30", "price_delta": 0.12, "vol": 120000},
            # !! 资金抢跑异动 !!
            {"ts": "14:01:45", "price_delta": 0.25, "vol": 250000},
            {"ts": "14:02:00", "price_delta": 0.42, "vol": 380000},
            {"ts": "14:02:15", "price_delta": 0.55, "vol": 520000},
            {"ts": "14:02:30", "price_delta": 0.65, "vol": 450000},
            # 冲高后震荡
            {"ts": "14:02:45", "price_delta": 0.58, "vol": 320000},
            {"ts": "14:03:00", "price_delta": 0.62, "vol": 280000},
            {"ts": "14:03:15", "price_delta": 0.50, "vol": 200000},
            {"ts": "14:03:30", "price_delta": 0.55, "vol": 180000},
            {"ts": "14:03:45", "price_delta": 0.60, "vol": 150000},
            {"ts": "14:04:00", "price_delta": 0.58, "vol": 130000},
        ],
        "news": [
            {
                "ts": "13:50:00", "source": "东方财富股吧",
                "content": "核电板块最近异动频繁，是不是年底有项目审批消息？",
                "type": "social"
            },
            {
                "ts": "14:01:10", "source": "知名核能行业自媒体",
                "content": "独家获悉：内蒙古某核电项目环评已通过，预计近日正式获批",
                "type": "rumor"
            },
            {
                "ts": "14:01:50", "source": "Level-2资金监控",
                "content": "中国核电出现异常大单扫货，疑似有资金提前获得项目审批信息",
                "type": "capital"
            },
            {
                "ts": "14:02:20", "source": "微博财经大V",
                "content": "核电板块集体躁动！市场传闻新一批核电项目即将获批，中国核电最受益",
                "type": "social"
            },
            {
                "ts": "14:03:00", "source": "财联社电报",
                "content": "【关注】核电板块午后大幅拉升，中国核电一度涨超7%。市场消息称新核电项目审批或将加速。",
                "type": "official"
            },
        ],
        "precomputed_kg": {
            "summary": "【核心结论】内幕消息驱动的资金抢跑。14:01:10 核能自媒体爆出项目环评通过消息后，14:01:45 开始出现异常大单扫货（疑似消息知情方），随后散户+游资跟风涌入，股价2分钟内从8.58拉升至9.15（+6.6%）。核心驱动力是市场对核电审批加速的预期差。",
            "nodes": [
                {"id": "中国核电(sh.601985)", "group": "stock"},
                {"id": "核电项目审批加速", "group": "concept"},
                {"id": "行业自媒体爆料", "group": "source"},
                {"id": "异常大单资金", "group": "capital"},
                {"id": "散户+游资跟风", "group": "action"}
            ],
            "links": [
                {"source": "行业自媒体爆料", "target": "核电项目审批加速", "value": "独家信息首发披露"},
                {"source": "核电项目审批加速", "target": "中国核电(sh.601985)", "value": "直接受益上市标的"},
                {"source": "异常大单资金", "target": "中国核电(sh.601985)", "value": "疑似消息知情方抢跑"},
                {"source": "散户+游资跟风", "target": "中国核电(sh.601985)", "value": "短线资金蜂拥放大波动"}
            ],
            "cot": [
                "1. [消息溯源]: 14:01:10 - 核能行业自媒体爆出内蒙古核电项目环评通过，消息具有独家性。",
                "2. [资金异常]: 14:01:45 - 出现显著异常大单扫货，早于主流媒体报道，疑似消息知情方提前行动。",
                "3. [传播扩散]: 14:02:20 微博大V转发传闻，信息开始在散户群体中快速扩散。",
                "4. [盘面验证]: 14:01:45至14:02:15 成交量暴增4-5倍，连续大单扫货推升股价。",
                "5. [归因收敛]: 确定为『行业独家消息→知情资金抢跑→社交媒体扩散→散户跟风放大』的消息博弈型异动。"
            ]
        }
    },
    {
        "case_id": "case_005_btc_etf",
        "symbol": "crypto.btc",
        "symbol_name": "比特币",
        "case_date": "2024-01-10",
        "description": "SEC正式批准比特币现货ETF，BTC瞬间拉升后回落，上演典型的'Buy the rumor, sell the news'",
        "anomaly_type": "监管事件-预期兑现型",
        "base_price": 46200.00,
        "ticks": [
            {"ts": "21:00:00", "price_delta": 0, "vol": 1200},
            {"ts": "21:00:30", "price_delta": 50, "vol": 980},
            {"ts": "21:01:00", "price_delta": 100, "vol": 1100},
            {"ts": "21:01:30", "price_delta": 80, "vol": 1500},
            {"ts": "21:02:00", "price_delta": 150, "vol": 2800},
            {"ts": "21:02:30", "price_delta": 350, "vol": 5200},
            # !! SEC 批准消息传出 !!
            {"ts": "21:03:00", "price_delta": 1200, "vol": 25000},
            {"ts": "21:03:30", "price_delta": 2500, "vol": 48000},
            {"ts": "21:04:00", "price_delta": 2800, "vol": 52000},
            # 冲高回落 (Sell the news)
            {"ts": "21:04:30", "price_delta": 2200, "vol": 38000},
            {"ts": "21:05:00", "price_delta": 1500, "vol": 32000},
            {"ts": "21:05:30", "price_delta": 800, "vol": 28000},
            {"ts": "21:06:00", "price_delta": 500, "vol": 22000},
            {"ts": "21:06:30", "price_delta": 300, "vol": 18000},
            {"ts": "21:07:00", "price_delta": -200, "vol": 15000},
            {"ts": "21:07:30", "price_delta": -500, "vol": 12000},
            {"ts": "21:08:00", "price_delta": -300, "vol": 10000},
        ],
        "news": [
            {
                "ts": "20:55:00", "source": "Bloomberg",
                "content": "传SEC已完成比特币现货ETF审批流程，预计今晚公布结果",
                "type": "rumor"
            },
            {
                "ts": "21:02:00", "source": "Twitter/X加密KOL",
                "content": "BREAKING: Multiple sources confirm SEC has approved spot Bitcoin ETFs",
                "type": "breaking"
            },
            {
                "ts": "21:03:10", "source": "SEC官方声明",
                "content": "SEC正式批准11只比特币现货ETF上市交易，这是加密货币监管的里程碑时刻",
                "type": "official"
            },
            {
                "ts": "21:04:20", "source": "CoinDesk",
                "content": "比特币ETF获批后价格冲高至49000美元，但交易员提醒注意'Sell the news'风险",
                "type": "analysis"
            },
            {
                "ts": "21:05:30", "source": "知名交易员",
                "content": "经典的利好出尽。BTC ETF获批是个月度级别的顶部信号，长期机构资金需要时间入场",
                "type": "analysis"
            },
        ],
        "precomputed_kg": {
            "summary": "【核心结论】监管里程碑事件引发'利好出尽'行情。21:03:10 SEC正式批准比特币现货ETF，BTC 1分钟内暴涨2800美元至49000（+6%），但随即上演经典的'Buy the rumor, sell the news'，15分钟内回吐全部涨幅并转跌。",
            "nodes": [
                {"id": "比特币(BTC)", "group": "stock"},
                {"id": "SEC批准现货ETF", "group": "policy"},
                {"id": "SEC官方+Bloomberg", "group": "source"},
                {"id": "短线获利盘", "group": "capital"},
                {"id": "冲高回落", "group": "action"},
                {"id": "Buy the rumor, sell the news", "group": "pattern"}
            ],
            "links": [
                {"source": "SEC官方+Bloomberg", "target": "SEC批准现货ETF", "value": "监管里程碑正式确认"},
                {"source": "SEC批准现货ETF", "target": "比特币(BTC)", "value": "长期利好但已被充分定价"},
                {"source": "短线获利盘", "target": "冲高回落", "value": "消息兑现后集中获利了结"},
                {"source": "冲高回落", "target": "比特币(BTC)", "value": "15分钟回吐全部涨幅"},
                {"source": "Buy the rumor, sell the news", "target": "冲高回落", "value": "经典市场行为模式"}
            ],
            "cot": [
                "1. [预期积累]: 20:55 Bloomberg已传出审批完成消息，市场预期高度一致。",
                "2. [事件确认]: 21:03:10 - SEC官方正式批准11只BTC现货ETF，靴子落地。",
                "3. [脉冲式冲高]: 21:03:00-21:04:00 BTC从46350暴涨至49000，成交量放大40倍。",
                "4. [利好出尽]: 21:04:30起短线获利盘集中抛售，价格快速回落。",
                "5. [归因收敛]: 确定为『监管利好兑现→预期充分定价→短线获利了结→利好出尽回落』的经典预期差行情。"
            ]
        }
    }
]


def generate_ohlc(base_price: float, price_delta: float, is_volatile: bool = False):
    """根据基准价格和变动量生成真实感的 OHLC 数据"""
    price = base_price + price_delta
    spread = abs(price_delta) * 0.3 if abs(price_delta) > 1 else 0.5
    noise = random.uniform(-spread * 0.5, spread * 0.5)
    
    open_p = price - random.uniform(0, spread * 0.8)
    close_p = price + noise
    high_p = max(open_p, close_p) + random.uniform(0, spread)
    low_p = min(open_p, close_p) - random.uniform(0, spread)
    
    return round(open_p, 2), round(high_p, 2), round(low_p, 2), round(close_p, 2)


def prepare_case(case: dict, output_dir: str):
    """将一个案例的数据写入 SQLite"""
    db_path = os.path.join(output_dir, case["case_id"], "timeseries.db")
    meta_path = os.path.join(output_dir, case["case_id"], "meta.json")
    kg_path = os.path.join(output_dir, case["case_id"], "precomputed_kg.json")
    
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 初始化数据库
    db = TimeSeriesDB(db_path)
    
    # 写入 Tick 数据
    tick_records = []
    for t in case["ticks"]:
        op, hi, lo, cl = generate_ohlc(case["base_price"], t["price_delta"])
        tick_records.append({
            "symbol": case["symbol"],
            "timestamp": t["ts"],
            "price": round(case["base_price"] + t["price_delta"], 2),
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
            "volume": t["vol"],
            "amount": round(t["vol"] * (case["base_price"] + t["price_delta"]), 2)
        })
    
    tick_count = db.insert_ticks(tick_records)
    
    # 写入资讯数据
    news_records = []
    for n in case["news"]:
        news_records.append({
            "symbol": case["symbol"],
            "timestamp": n["ts"],
            "source": n["source"],
            "content": n["content"],
            "news_type": n["type"]
        })
    
    news_count = db.insert_news(news_records)
    
    # 写入元信息
    db.set_case_meta(
        symbol=case["symbol"],
        symbol_name=case["symbol_name"],
        case_date=case["case_date"],
        description=case["description"],
        anomaly_type=case["anomaly_type"]
    )
    
    # 保存元信息 JSON（供前端使用）
    meta = {
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "symbol_name": case["symbol_name"],
        "case_date": case["case_date"],
        "description": case["description"],
        "anomaly_type": case["anomaly_type"],
        "tick_count": tick_count,
        "news_count": news_count
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    # 保存预计算知识图谱（作为 LLM 不可用时的 fallback）
    with open(kg_path, 'w', encoding='utf-8') as f:
        json.dump(case["precomputed_kg"], f, ensure_ascii=False, indent=2)
    
    db.close()
    
    print(f"  ✓ {case['case_id']}: {tick_count} ticks, {news_count} news → {db_path}")
    return meta


def main():
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cases')
    
    print("=" * 60)
    print("  盘中异动归因引擎 — 案例数据准备")
    print("=" * 60)
    print(f"\n输出目录: {os.path.abspath(output_dir)}\n")
    
    all_meta = []
    for case in CASES:
        meta = prepare_case(case, output_dir)
        all_meta.append(meta)
    
    # 写入案例汇总清单
    index_path = os.path.join(output_dir, "cases_index.json")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(all_meta, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"  完成！共准备 {len(all_meta)} 个案例。")
    print(f"  案例索引: {os.path.abspath(index_path)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
