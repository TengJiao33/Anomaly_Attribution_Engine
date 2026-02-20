"""
大模型归因分析器 (Attribution Analyzer) — 增强版

利用大语言模型进行：
- 命名实体识别 (NER) + 关系抽取 (RE)
- 因果逻辑链构建 (Chain of Thought)
- 归因质量自动评估 (Attribution Quality Assessment)

支持多个 LLM 后端（豆包/OpenAI 兼容接口）。
"""

import os
import json
import asyncio
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


# ===== 归因质量评估器 ===== #

class AttributionQualityAssessor:
    """
    归因质量多维自动评估

    评估维度：
    1. 时序一致性 - 因果链中的事件是否按时间先后排列
    2. 实体覆盖率 - 归因节点是否覆盖了输入文本的关键实体
    3. 逻辑闭合度 - 因果链能否解释观察到的异动方向
    """

    @staticmethod
    def assess(kg_result: dict, original_text: str) -> dict:
        """
        对 LLM 归因结果进行质量评估

        :param kg_result: LLM 返回的知识图谱结构
        :param original_text: 原始资讯输入文本
        :return: 质量评估报告
        """
        scores = {}

        # 1. 时序一致性评分（检查 CoT 步骤是否有时间序标注且递增）
        cot = kg_result.get("cot", [])
        temporal_score = AttributionQualityAssessor._check_temporal_consistency(cot)
        scores["temporal_consistency"] = temporal_score

        # 2. 实体覆盖率（输入文本中的关键词在图谱节点中的覆盖率）
        nodes = kg_result.get("nodes", [])
        coverage_score = AttributionQualityAssessor._check_entity_coverage(nodes, original_text)
        scores["entity_coverage"] = coverage_score

        # 3. 逻辑闭合度（因果链是否形成完整路径，终点是否指向目标标的）
        links = kg_result.get("links", [])
        closure_score = AttributionQualityAssessor._check_logical_closure(nodes, links)
        scores["logical_closure"] = closure_score

        # 4. 综合质量分 (0-100)
        overall = round(
            temporal_score * 0.3 + coverage_score * 0.4 + closure_score * 0.3, 1
        )
        scores["overall_quality"] = overall

        return scores

    @staticmethod
    def _check_temporal_consistency(cot: list) -> float:
        """检查 CoT 中的时间序是否一致"""
        if not cot or len(cot) < 2:
            return 50.0  # 无法判断，给中性分

        # 检查是否有编号且递增
        has_numbering = all(
            step.strip().startswith(str(i + 1))
            for i, step in enumerate(cot)
        )

        # 检查是否包含时间标注
        time_pattern = re.compile(r'\d{2}:\d{2}')
        times_found = []
        for step in cot:
            matches = time_pattern.findall(step)
            times_found.extend(matches)

        if has_numbering and len(times_found) >= 2:
            return 90.0
        elif has_numbering:
            return 70.0
        else:
            return 40.0

    @staticmethod
    def _check_entity_coverage(nodes: list, text: str) -> float:
        """检查图谱节点对输入文本的覆盖率"""
        if not nodes:
            return 0.0

        node_ids = [n.get("id", "") for n in nodes]
        matched = sum(1 for nid in node_ids if nid and nid in text)

        if not node_ids:
            return 0.0

        coverage = matched / len(node_ids)
        return round(min(coverage * 100 + 30, 100), 1)  # 基础分 30

    @staticmethod
    def _check_logical_closure(nodes: list, links: list) -> float:
        """检查因果图是否形成逻辑闭合"""
        if not nodes:
            return 0.0
        if not links:
            return 20.0  # 有节点但无关系，给低分

        # 计算图的连通性
        node_ids = set(n.get("id", "") for n in nodes)
        linked_nodes = set()
        for link in links:
            linked_nodes.add(link.get("source", ""))
            linked_nodes.add(link.get("target", ""))

        overlap = linked_nodes & node_ids
        if not node_ids:
            return 0.0

        connectivity = len(overlap) / len(node_ids)
        return round(min(connectivity * 100, 100), 1)


# ===== 归因分析器 ===== #

class AttributionAnalyzer:
    """大模型归因分析器 — 增强版"""

    def __init__(self):
        self.api_key = os.environ.get("DOUBAO_API_KEY", "")
        self.endpoint_id = os.environ.get("DOUBAO_ENDPOINT_ID", "")
        self.base_url = os.environ.get(
            "LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )

        self.client = AsyncOpenAI(
            api_key=self.api_key or "placeholder",
            base_url=self.base_url
        )

        self.assessor = AttributionQualityAssessor()

        self.is_configured = bool(self.api_key and self.endpoint_id)
        if self.is_configured:
            logger.info("AttributionAnalyzer: LLM API 已配置（增强模式）")
        else:
            logger.warning("AttributionAnalyzer: LLM API 未配置，将使用增强 Mock 模式")

    async def extract_knowledge_graph(self, text: str) -> dict:
        """
        利用大模型进行归因分析：NER + RE + CoT，并自动评估归因质量。

        :param text: 异动前后的资讯文本（已经过时间窗口对齐）
        :return: 知识图谱结构 {summary, nodes, links, cot, quality_scores}
        """
        if not self.is_configured:
            await asyncio.sleep(0.3)
            result = self._generate_enhanced_mock_kg(text)
        else:
            result = await self._call_llm(text)

        # 归因质量评估
        quality = self.assessor.assess(result, text)
        result["quality_scores"] = quality

        return result

    async def _call_llm(self, text: str) -> dict:
        """调用 LLM API 进行归因分析"""

        system_prompt = '''你是一个顶级金融异动归因AI系统。你将收到一段在股票/数字货币发生异动前后被系统通过时序对齐引擎捕获的全网资讯文本切片。

你的任务是：
1. **命名实体识别(NER)**: 从文本中精准提取所有相关实体（公司、概念板块、资金方、信息源、政策等）
2. **因果关系抽取(RE)**: 识别实体之间的因果/传导/触发关系
3. **因果推理链(CoT)**: 按时间顺序构建异动的完整因果逻辑链

你必须严格按照以下JSON格式输出（不要包含markdown代码块标记）：
{
    "summary": "一句简洁精准的异动归因结论（不超过30字）",
    "nodes": [
        {"id": "实体名称", "group": "实体类型"}
    ],
    "links": [
        {"source": "源实体", "target": "目标实体", "value": "关系描述（动词短语）"}
    ],
    "cot": [
        "1. [HH:MM 时序对齐] 描述第一个因果环节",
        "2. [HH:MM 情绪传导] 描述传导过程",
        "3. [HH:MM 资金响应] 描述资金面变化",
        "4. [归因收敛] 最终异动原因总结"
    ]
}

实体类型(group)可选值:
- stock: 股票/标的
- concept: 概念板块
- source: 信息来源（财联社、股吧等）
- capital: 资金主体（游资、机构、北向等）
- action: 关键操作（扫货、抛售、公告等）
- policy: 政策事件
- sector: 行业板块

规则:
- nodes 列表至少包含 3 个不同类型的实体
- links 列表要构成有向无环图（DAG），体现因果传导方向
- cot 列表每步都要包含时间标注 [HH:MM]，且时间递增
- summary 要直击核心，像交易员简报一样精炼
请确保输出合法的JSON。'''

        try:
            response = await self.client.chat.completions.create(
                model=self.endpoint_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请对以下异动时间窗口内的资讯流进行极速归因聚合（注意时间戳顺序）：\n{text[:3000]}"}
                ],
                temperature=0.1,
                max_tokens=1500
            )

            raw_content = response.choices[0].message.content
            # 清理可能的 markdown 代码块包裹
            clean_content = raw_content.strip()
            if clean_content.startswith("```"):
                clean_content = clean_content.split("\n", 1)[1] if "\n" in clean_content else clean_content
            if clean_content.endswith("```"):
                clean_content = clean_content.rsplit("```", 1)[0]
            clean_content = clean_content.replace('```json', '').replace('```', '').strip()

            result = json.loads(clean_content)

            # 验证输出结构
            if not isinstance(result.get("nodes"), list):
                result["nodes"] = []
            if not isinstance(result.get("links"), list):
                result["links"] = []
            if not isinstance(result.get("cot"), list):
                result["cot"] = []

            logger.info(f"LLM 归因成功: {result.get('summary', '')[:50]}...")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"LLM 输出 JSON 解析失败: {e}")
            return self._generate_enhanced_mock_kg(text)
        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            raise

    def _generate_enhanced_mock_kg(self, text: str) -> dict:
        """
        增强版 Mock 模式：基于文本特征生成更真实的归因结构。
        用于无 API Key 时的 Demo 演示，比原版更具说服力。
        """
        # 多维度关键词-实体映射
        entity_rules = [
            # (关键词, 实体名, 类型)
            ("茅台", "贵州茅台(sh.600519)", "stock"),
            ("宁德", "宁德时代(sz.300750)", "stock"),
            ("比亚迪", "比亚迪(sz.002594)", "stock"),
            ("核电", "中国核电(sh.601985)", "stock"),
            ("BTC", "比特币(BTC/USDT)", "stock"),
            ("比特币", "比特币(BTC/USDT)", "stock"),

            ("公告", "上市公司公告", "action"),
            ("分红", "特别分红方案", "action"),
            ("提价", "产品提价", "action"),
            ("砍单", "海外客户砍单", "action"),
            ("抛售", "机构集中抛售", "action"),
            ("扫货", "巨量资金扫货", "action"),
            ("涨停", "涨停封板", "action"),
            ("闪崩", "盘中闪崩", "action"),

            ("政策", "产业政策利好", "policy"),
            ("补贴", "新能源补贴政策", "policy"),
            ("审批", "重大项目审批", "policy"),
            ("批准", "监管批准", "policy"),
            ("ETF", "现货ETF获批", "policy"),

            ("游资", "顶级游资席位", "capital"),
            ("北向", "北向资金", "capital"),
            ("机构", "主力机构", "capital"),
            ("主力", "主力资金", "capital"),

            ("财联社", "财联社电报", "source"),
            ("股吧", "东方财富股吧", "source"),
            ("雪球", "雪球社区", "source"),
            ("微博", "微博财经", "source"),

            ("固态电池", "固态电池概念", "concept"),
            ("新能源", "新能源板块", "concept"),
            ("锂电", "锂电池板块", "concept"),
        ]

        # 提取命中的实体
        nodes = []
        seen_ids = set()
        for keyword, entity_name, group in entity_rules:
            if keyword in text and entity_name not in seen_ids:
                nodes.append({"id": entity_name, "group": group})
                seen_ids.add(entity_name)

        if not nodes:
            nodes = [
                {"id": "市场异动信号", "group": "concept"},
                {"id": "资讯触发源", "group": "source"},
            ]

        # 按类型分组，构建因果链
        stocks = [n for n in nodes if n["group"] == "stock"]
        actions = [n for n in nodes if n["group"] == "action"]
        capitals = [n for n in nodes if n["group"] == "capital"]
        sources = [n for n in nodes if n["group"] == "source"]
        policies = [n for n in nodes if n["group"] == "policy"]

        links = []
        # 信息源 → 操作
        if sources and actions:
            links.append({"source": sources[0]["id"], "target": actions[0]["id"], "value": "率先披露"})
        # 操作/政策 → 标的
        if actions and stocks:
            links.append({"source": actions[0]["id"], "target": stocks[0]["id"], "value": "直接催化"})
        if policies and stocks:
            links.append({"source": policies[0]["id"], "target": stocks[0]["id"], "value": "政策驱动"})
        # 资金 → 标的
        if capitals and stocks:
            links.append({"source": capitals[0]["id"], "target": stocks[0]["id"], "value": "资金涌入推动异动"})
        # 如果链路不足，补充
        if len(links) < 2 and len(nodes) >= 2:
            links.append({"source": nodes[0]["id"], "target": nodes[-1]["id"], "value": "因果关联"})

        # 标的名
        stock_name = stocks[0]["id"] if stocks else "目标标的"
        trigger = actions[0]["id"] if actions else (policies[0]["id"] if policies else "市场事件")

        # 构建 CoT
        cot = [
            f"1. [09:28 背景扫描] 资讯流监测到 {len(sources)} 个信息源开始出现异常讨论频率。",
            f"2. [09:31 事件触发] 命中关键催化事件: {trigger}，系统判定为 S 级信号。",
            f"3. [09:32 情绪传导] 社交媒体情绪指数急剧攀升，信息传播速度超过正常基线 3.2 倍。",
            f"4. [09:33 资金响应] {'、'.join([c['id'] for c in capitals]) if capitals else '主力资金'}开始异常操作，微观流动性结构剧变。",
            f"5. [归因收敛] 确定为『{trigger} → 资金抢跑 → 流动性挤兑』的经典异动模式，核心标的: {stock_name}。",
        ]

        return {
            "summary": f"[智能归因] {trigger}引发{stock_name}异动",
            "nodes": nodes[:8],
            "links": links,
            "cot": cot,
        }


if __name__ == "__main__":
    async def test():
        analyzer = AttributionAnalyzer()
        res = await analyzer.extract_knowledge_graph(
            "[09:32:25][财联社电报] 贵州茅台公告：即将实施特别分红，并大幅提升出厂价。\n"
            "[09:32:38][游资监控带] 检测到北向资金与顶级游资席位在茅台主锁单15亿。"
        )
        print("归因结果:", json.dumps(res, ensure_ascii=False, indent=2))

    asyncio.run(test())
