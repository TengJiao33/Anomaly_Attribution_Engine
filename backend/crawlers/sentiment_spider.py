import aiohttp
import asyncio
import random
import re
from bs4 import BeautifulSoup

class SentimentSpider:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }

    async def fetch_eastmoney_guba(self, symbol: str, limit: int = 50) -> list:
        """
        异步提取东方财富股吧帖子
        :param symbol: 股票代码如 '600519'
        :param limit: 获取帖子的大致条数
        :return: 帖子文本列表
        """
        clean_code = re.sub(r'[^0-9]', '', symbol)
        if not clean_code:
            return []

        base_url = f"https://guba.eastmoney.com/list,{clean_code}.html"
        posts = []
        page = 1
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while len(posts) < limit and page <= 5: # 最多爬 5 页
                url = f"https://guba.eastmoney.com/list,{clean_code}_{page}.html" if page > 1 else base_url
                try:
                    async with session.get(url, timeout=10) as resp:
                        text = await resp.text(encoding='utf-8', errors='ignore')
                        soup = BeautifulSoup(text, 'html.parser')
                        
                        title_elements = soup.select(".title a") or soup.find_all('a', class_='note')
                        
                        for el in title_elements:
                            title = el.get_text(strip=True)
                            if title and len(title) > 5:
                                posts.append(title)
                                if len(posts) >= limit:
                                    break
                    page += 1
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    print(f"Fetch guba error on page {page}: {e}")
                    break
                    
        return posts

if __name__ == "__main__":
    async def test():
        spider = SentimentSpider()
        docs = await spider.fetch_eastmoney_guba("600519", limit=20)
        for idx, d in enumerate(docs):
            print(f"{idx+1}. {d}")
    asyncio.run(test())
