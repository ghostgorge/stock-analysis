"""阶段0:情绪闸门 + 日历闸门。
情绪判定输出 {ice|warming|climax|ebbing},日历闸门读 data/calendar_ipo.csv。
csv格式: name,code,raise_amount,subscribe_date,payment_date,chain_boards
chain_boards 用|分隔,例: 半导体|存储器|封测
(该csv可手工维护,也可写个ak.stock_xgsglb_em()的更新脚本)"""
from __future__ import annotations
import os
from datetime import date, timedelta
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def sentiment_gate(src) -> dict:
    """基于快照的粗粒度情绪判定。涨跌停家数、赚钱效应等更精细的代理
    指标可后续接龙虎榜/涨停池数据源增强,先保证判定可复现。"""
    snap = src.snapshot()
    up = int((snap["close"].notna() & (snap.get("pct_chg", pd.Series(dtype=float)) if "pct_chg" in snap else pd.Series(dtype=float)).ge(9.8)).sum()) if "pct_chg" in snap else None
    # 简化实现:用上证指数与其MA20/MA5的位置关系定档
    idx = src.daily("000001", 30) if hasattr(src, "index_daily") is False else src.index_daily("sh000001", 30)
    close = idx["close"]
    ma5, ma20 = close.rolling(5).mean().iloc[-1], close.rolling(20).mean().iloc[-1]
    last = close.iloc[-1]
    if last > ma5 > ma20:
        mood = "warming"
    elif last > ma20:
        mood = "warming"
    elif last < ma20 and last < ma5:
        mood = "ebbing"
    else:
        mood = "ice"
    return {"mood": mood, "limit_up_count": up}


def calendar_gate(params: dict, today: date | None = None) -> dict:
    today = today or date.today()
    path = os.path.join(DATA_DIR, "calendar_ipo.csv")
    result = {"hit": False, "detail": None, "excluded_boards": []}
    if not os.path.exists(path):
        result["detail"] = "calendar_ipo.csv缺失,日历闸门未生效(合规自检将标注)"
        return result
    cal = pd.read_csv(path, parse_dates=["subscribe_date", "payment_date"])
    cg = params["calendar_gate"]
    for _, row in cal.iterrows():
        if row["raise_amount"] < cg["mega_ipo_threshold"]:
            continue
        w_start = row["subscribe_date"].date() - timedelta(days=cg["window_before_subscribe_days"])
        w_end = row["payment_date"].date() + timedelta(days=cg["window_after_payment_days"])
        if w_start <= today <= w_end:
            result["hit"] = True
            result["detail"] = f"{row['name']}({row['code']}) 申购{row['subscribe_date'].date()} 缴款{row['payment_date'].date()}"
            result["excluded_boards"] += str(row["chain_boards"]).split("|")
    return result
