"""数据适配层。策略代码只依赖本模块的三个函数,数据源可插拔。

实现A: AkshareSource —— pip install akshare 后本地直接可用(免费,东财数据)
实现B: TdxMcpSource  —— 占位。你的通达信MCP接入Claude Code后,
       由Claude Code在会话中调MCP工具取数并落地为本模块约定的parquet格式,
       脚本从 data/cache/ 读取。策略代码零改动。

统一数据契约:
  snapshot(): DataFrame[code, name, close, market_cap, avg_amount_20d, listed_days, is_st]
  daily(code, days): DataFrame[date, open, high, low, close, volume, amount] 前复权,升序
  hot_boards(): list[str] 近5日有持续赚钱效应的板块名
"""
from __future__ import annotations
import os
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")


class AkshareSource:
    def __init__(self):
        import akshare as ak  # 延迟导入
        self.ak = ak

    def snapshot(self) -> pd.DataFrame:
        spot = self.ak.stock_zh_a_spot_em()
        df = pd.DataFrame({
            "code": spot["代码"],
            "name": spot["名称"],
            "close": spot["最新价"],
            "market_cap": spot["总市值"],
            "amount": spot["成交额"],
        })
        df["is_st"] = df["name"].str.contains("ST|退", na=False)
        # avg_amount_20d 与 listed_days 需逐票日线,留给stage1对入围者精确复核;
        # 快照层先用当日成交额粗筛(宽进,stage1终检严出)。
        df["avg_amount_20d"] = df["amount"]
        df["listed_days"] = 9999  # 精确值在daily()阶段校验
        return df

    def daily(self, code: str, days: int = 120) -> pd.DataFrame:
        hist = self.ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        df = pd.DataFrame({
            "date": pd.to_datetime(hist["日期"]),
            "open": hist["开盘"], "high": hist["最高"], "low": hist["最低"],
            "close": hist["收盘"], "volume": hist["成交量"], "amount": hist["成交额"],
        }).sort_values("date").reset_index(drop=True)
        return df.tail(days + 60).reset_index(drop=True)  # 多留60日算指标暖机

    def hot_boards(self) -> list[str]:
        bd = self.ak.stock_board_industry_name_em()
        # 简化代理:当日板块涨幅榜前列。持续性判定(近5日赚钱效应)建议
        # 缓存每日榜单后跨日比对——见 stage0_gate.persist_board_rank()。
        return bd.sort_values("涨跌幅", ascending=False)["板块名称"].head(8).tolist()


class TdxMcpSource:
    """通达信MCP模式:Claude Code调用MCP工具后把结果写入 data/cache/,
    本类只读缓存,保证策略层与取数方式解耦。"""

    def snapshot(self) -> pd.DataFrame:
        return pd.read_parquet(os.path.join(CACHE_DIR, "snapshot.parquet"))

    def daily(self, code: str, days: int = 120) -> pd.DataFrame:
        return pd.read_parquet(os.path.join(CACHE_DIR, f"daily_{code}.parquet")).tail(days + 60)

    def hot_boards(self) -> list[str]:
        with open(os.path.join(CACHE_DIR, "hot_boards.txt"), encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]


def get_source(name: str = "akshare"):
    return AkshareSource() if name == "akshare" else TdxMcpSource()
