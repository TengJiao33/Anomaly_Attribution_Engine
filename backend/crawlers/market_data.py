import baostock as bs
import pandas as pd
from datetime import datetime, timedelta

class MarketDataCrawler:
    def __init__(self):
        # 登录系统
        self.lg = bs.login()
        if self.lg.error_code != '0':
            print('BaoStock login failed:', self.lg.error_msg)
        else:
            print('BaoStock login success.')

    def get_k_data(self, code: str, start_date: str, end_date: str, frequency: str = 'd') -> pd.DataFrame:
        """
        获取K线数据
        :param code: 股票代码，如 'sh.600000'
        :param start_date: 开始日期 'YYYY-MM-DD'
        :param end_date: 结束日期 'YYYY-MM-DD'
        :param frequency: 数据频率，支持 'd'(日), 'w'(周), 'm'(月), '5'(5分钟), '15'(15分钟), '30'(30分钟), '60'(60分钟)
        :return: DataFrame
        """
        rs = bs.query_history_k_data_plus(
            code,
            "date,time,code,open,high,low,close,volume,amount,adjustflag",
            start_date=start_date, end_date=end_date,
            frequency=frequency, adjustflag="3" # 3：默认不复权
        )
        data_list = []
        while (rs.error_code == '0') and rs.next():
            data_list.append(rs.get_row_data())
            
        result = pd.DataFrame(data_list, columns=rs.fields)
        # 转换数据类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors='coerce')
                
        return result

    def logout(self):
        bs.logout()

if __name__ == "__main__":
    crawler = MarketDataCrawler()
    # 测试获取三天的数据
    end = datetime.now()
    start = end - timedelta(days=3)
    df = crawler.get_k_data("sh.600519", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), frequency="15")
    print(df.tail())
    crawler.logout()
