"""阶段2:右侧确认四判据。全部为"已发生"事实的代码化判定。
本文件即v2提示词的"判定逻辑冻结"——改这里必须走git+回测,盘中改动会被合规自检的代码hash比对暴露。
判定为v0启发式实现,阈值全部来自params.yaml,请用历史三买案例回测校准后再实盘。"""
from __future__ import annotations
import pandas as pd
from indicators import enrich, gmma


def _find_breakout(d: pd.DataFrame, p: dict) -> int | None:
    """近N日内寻找有效突破日:放量长阳突破前30日平台上沿,此后收盘未回落至突破K开盘价下。
    返回突破日的iloc索引,无则None。"""
    n = p["breakout_lookback_days"]
    for i in range(len(d) - 1, len(d) - 1 - n, -1):
        if i < p["platform_min_days"] + 1:
            break
        row = d.iloc[i]
        platform = d.iloc[i - p["platform_min_days"]: i]
        platform_top = platform["high"].max()
        if (
            row["close"] > platform_top
            and row["close"] > row["open"]
            and row["volume"] >= p["breakout_vol_ratio"] * row["vol_ma20"]
            and (d.iloc[i:]["close"] >= row["open"]).all()
        ):
            return i
    return None


def _check_pullback(d: pd.DataFrame, bo_idx: int, p: dict) -> dict | None:
    """三买判定:突破后缩量回踩不破平台上沿(容忍3%),且已再收阳。
    返回 {pullback_low, platform_top, confirm_date} 或 None。"""
    bo = d.iloc[bo_idx]
    platform_top = d.iloc[bo_idx - p["platform_min_days"]: bo_idx]["high"].max()
    after = d.iloc[bo_idx + 1:]
    if len(after) < 2:
        return None
    pull = after[after["close"] < bo["close"]]
    if pull.empty:
        return None  # 尚无回踩,不合格(结构未走完)
    pb_low = pull["low"].min()
    pb_vol_ok = pull["volume"].max() <= p["pullback_vol_max_ratio"] * bo["volume"]
    hold_ok = pb_low >= platform_top * (1 - p["platform_pierce_tolerance_pct"] / 100)
    pb_end_idx = pull.index[-1]
    rebound = d.loc[pb_end_idx + 1:] if pb_end_idx + 1 in d.index else pd.DataFrame()
    rebound_ok = (not rebound.empty) and bool(
        ((rebound["close"] > rebound["open"]) & (rebound["close"] > rebound["close"].shift(1).fillna(0))).any()
    )
    if pb_vol_ok and hold_ok and rebound_ok:
        confirm = rebound[(rebound["close"] > rebound["open"])].iloc[0]
        return {"pullback_low": float(pb_low), "platform_top": float(platform_top),
                "confirm_date": str(confirm["date"].date())}
    return None


def stage2_check(daily: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    p = params["stage2"]
    d = enrich(daily).reset_index(drop=True)
    last = d.iloc[-1]
    hits, detail = 0, {}

    bo_idx = _find_breakout(d, p)
    detail["c1_breakout"] = bo_idx is not None
    if bo_idx is not None:
        hits += 1
        detail["breakout_date"] = str(d.iloc[bo_idx]["date"].date())

    pb = _check_pullback(d, bo_idx, p) if bo_idx is not None else None
    detail["c2_pullback_confirmed"] = pb is not None   # 必要条件
    if pb:
        hits += 1
        detail.update(pb)

    ma_stack = last["ma5"] > last["ma10"] > last["ma20"]
    stack_series = (d["ma5"] > d["ma10"]) & (d["ma10"] > d["ma20"])
    first_stack = ma_stack and not stack_series.iloc[-61:-1].all() and stack_series.tail(1).item()
    macd_ok = last["dif"] > 0 and last["dea"] > 0
    detail["c3_ma_macd"] = bool(first_stack and macd_ok)
    if detail["c3_ma_macd"]:
        hits += 1

    adx_now, adx_prev = last["adx"], d["adx"].iloc[-6]
    adx_ok = p["adx_start_min"] <= adx_now <= p["adx_start_max"] and adx_now > adx_prev
    _, _, spread = gmma(d["close"])
    gmma_ok = p["gmma_spread_min_pct"] <= spread.iloc[-1] <= p["gmma_spread_max_pct"]
    detail["c4_trend_start"] = bool(adx_ok and gmma_ok)
    detail["adx"] = round(float(adx_now), 2)
    if detail["c4_trend_start"]:
        hits += 1

    detail["hits"] = hits
    passed = hits >= p["min_criteria_hit"] and detail["c2_pullback_confirmed"]
    return passed, detail
