import os
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class AttributionAnalyzer:
    def __init__(self):
        # 兼容现有配置
        self.api_key = os.environ.get("DOUBAO_API_KEY", "")
        self.endpoint_id = os.environ.get("DOUBAO_ENDPOINT_ID", "")
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def extract_knowledge_graph(self, text: str) -> dict:
        """
        利用大模型进行归因分析：命名实体识别(NER)和关系抽取(RE)
        """
        if not self.api_key or not self.endpoint_id:
            # Fallback mock for demo purposes if no API key
            await asyncio.sleep(1) # Simulate network delay
            return {
                "nodes": [{"id": "消息源", "group": 1}, {"id": "散户资金", "group": 2}],
                "links": [{"source": "消息源", "target": "散户资金", "value": "引发跟风"}],
                "summary": "[Mock] 提取失败，API Key未配置。启用备用归因逻辑。"
            }
            
        system_prompt = '''
你是一个金融极速归因AI系统。输入一段全网资讯/股吧文本（盘中异动爆发点前的切片）。
你需要立刻抽取出这段资讯中的核心“实体（Entity）”以及“因果逻辑链条”，构建瞬时知识图谱。

请严格输出以下JSON格式（不要包含 markdown 代码块）：
{
    "summary": "一句简短的异动归因总结",
    "nodes": [
        {"id": "公司A", "group": "company"},
        {"id": "固态电池", "group": "concept"}
    ],
    "links": [
        {"source": "公司A", "target": "固态电池", "value": "披露技术突破"}
    ]
}
'''
        try:
            response = await self.client.chat.completions.create(
                model=self.endpoint_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请对以下资讯流进行极速归因聚合：\n{text[:1000]}"}
                ],
                temperature=0.1,
                max_tokens=250
            )
            
            raw_content = response.choices[0].message.content
            clean_content = raw_content.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_content)
        except Exception as e:
            print(f"AttributionAnalyzer API Error: {e}")
            return {
                "summary": f"大模型解析异常: {str(e)}",
                "nodes": [{"id": "系统", "group": "error"}],
                "links": []
            }

if __name__ == "__main__":
    async def test():
        analyzer = AttributionAnalyzer()
        res = await analyzer.extract_knowledge_graph("刚刚A公司发布公告宣布在固态电池技术上取得重大突破，随后游资疯狂涌入将股价拉至涨停。")
        print("Test:", res)
    asyncio.run(test())
