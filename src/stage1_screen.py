"""阶段1:硬性约束 + 数值粗筛。全部确定性计算,无任何自由裁量。
每只幸存者携带 source 字段(候选来源审计)——这是v2提示词纪律3的代码化。"""
from __future__ import annotations
import pandas as pd
from indicators import enrich


def universe_filter(snap: pd.DataFrame, params: dict) -> pd.DataFrame:
    u = params["universe"]
    df = snap.copy()
    df = df[df["code"].astype(str).str.startswith(tuple(u["boards_allowed"]))]
    df = df[~df["code"].astype(str).str.startswith(tuple(u["boards_excluded"]))]
    if u["exclude_st"]:
        df = df[~df["is_st"]]
    df = df[df["market_cap"] >= u["min_market_cap"]]
    df = df[df["avg_amount_20d"] >= u["min_avg_amount_20d"]]
    return df


def stage1_check(daily: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    """对单只个股的120日日线执行阶段1数值条件。返回(是否通过, 各项读数)。"""
    p, u = params["stage1"], params["universe"]
    if len(daily) < u["min_listed_days"]:
        return False, {"reject": "上市不足120日"}
    d = enrich(daily)
    last = d.iloc[-1]
    readings = {}
    readings["dist_ma20_pct"] = round((last["close"] / last["ma20"] - 1) * 100, 2)
    base60 = d["close"].iloc[-61] if len(d) > 61 else d["close"].iloc[0]
    readings["gain_60d_pct"] = round((last["close"] / base60 - 1) * 100, 2)
    recent = d.tail(p["crash_lookback_days"])
    readings["worst_3d_pct"] = round(recent["pct_chg"].min(), 2)
    readings["avg_amount_20d"] = float(d["amount"].tail(20).mean())

    ok = (
        last["close"] > last["ma20"]
        and 0 <= readings["dist_ma20_pct"] <= p["max_dist_ma20_pct"]
        and p["gain_60d_min_pct"] <= readings["gain_60d_pct"] <= p["gain_60d_max_pct"]
        and readings["worst_3d_pct"] > -p["crash_daily_drop_pct"]
        and readings["avg_amount_20d"] >= u["min_avg_amount_20d"]
    )
    if not ok:
        reasons = []
        if not (last["close"] > last["ma20"]):
            reasons.append("MA20下方")
        elif readings["dist_ma20_pct"] > p["max_dist_ma20_pct"]:
            reasons.append(f"距MA20 {readings['dist_ma20_pct']}%>8%")
        if not (p["gain_60d_min_pct"] <= readings["gain_60d_pct"] <= p["gain_60d_max_pct"]):
            reasons.append(f"60日涨幅{readings['gain_60d_pct']}%越界")
        if readings["worst_3d_pct"] <= -p["crash_daily_drop_pct"]:
            reasons.append(f"近3日大阴线{readings['worst_3d_pct']}%熔断")
        if readings["avg_amount_20d"] < u["min_avg_amount_20d"]:
            reasons.append("20日均额<2亿")
        readings["reject"] = ";".join(reasons)
    return ok, readings
