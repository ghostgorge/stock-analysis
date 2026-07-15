"""编排器:python runner.py [--source akshare|tdx]
产出 output/candidates_YYYYMMDD.json,内含:
  - 通过全部代码闸门、等待闸门3检索的候选(带全部读数与止损/仓位)
  - 观察清单(分类:风险超限/回踩未走完/压线降级)
  - 合规自检:params.yaml与stage2代码的sha256、扩池轮数、日历闸门结果
Claude Code只消费这个json,做闸门3检索与终榜报告。"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from datasource import get_source
from stage0_gate import sentiment_gate, calendar_gate
from stage1_screen import universe_filter, stage1_check
from stage2_structure import stage2_check
from stage3_risk import gate1_risk, borderline_check

ROOT = os.path.join(os.path.dirname(__file__), "..")


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="akshare")
    ap.add_argument("--boards", nargs="*", default=None, help="热点白名单,不传则用数据源hot_boards()")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "config", "params.yaml"), encoding="utf-8") as f:
        params = yaml.safe_load(f)

    compliance = {
        "params_sha256": sha256_of(os.path.join(ROOT, "config", "params.yaml")),
        "stage2_code_sha256": sha256_of(os.path.join(ROOT, "src", "stage2_structure.py")),
        "screen_rounds_used": 0,
        "hand_picked_candidates": 0,  # 架构上恒为0:候选只能来自universe_filter
    }

    src = get_source(args.source)

    # ── 阶段0 ──
    mood = sentiment_gate(src)
    cal = calendar_gate(params)
    compliance["calendar_gate"] = cal
    if mood["mood"] == "ice":
        _dump({"mood": mood, "candidates": [], "watchlist": [],
               "verdict": "冰点:只输出观察清单", "compliance": compliance})
        return

    hot = args.boards or src.hot_boards()
    excluded = set(cal["excluded_boards"])
    hot = [b for b in hot if b not in excluded]

    # ── 阶段1:快照层粗筛(单轮;第二轮=补充高景气主线,由--boards显式传入) ──
    snap = universe_filter(src.snapshot(), params)
    compliance["screen_rounds_used"] = 1
    # 板块过滤:此处按数据源能力实现个股-板块映射;akshare可用
    # ak.stock_board_industry_cons_em(板块名)取成分股。骨架先全池示意:
    pool = snap["code"].astype(str).tolist()[: params["stage1"]["candidate_target_max"] * 5]

    candidates, watchlist = [], []
    for code in pool:
        try:
            daily = src.daily(code, 120)
        except Exception as e:
            continue
        ok1, r1 = stage1_check(daily, params)
        if not ok1:
            continue
        ok2, r2 = stage2_check(daily, params)
        readings = {**r1, **r2, "code": code, "source": "screener:stage1"}
        if not ok2:
            if r2.get("c1_breakout") and not r2.get("c2_pullback_confirmed"):
                watchlist.append({**readings, "watch_type": "B:回踩未走完"})
            continue
        price = float(daily["close"].iloc[-1])
        g1 = gate1_risk(price, r2, params)
        readings.update(g1, price=price)
        if not g1["gate1_pass"]:
            watchlist.append({**readings, "watch_type": "A:风险%>8"})
            continue
        bl = borderline_check(readings, params)
        readings.update(bl)
        if bl["downgrade"]:
            watchlist.append({**readings, "watch_type": "C:多项压线"})
            continue
        candidates.append(readings)
        if len(candidates) >= params["stage2"]["list_b_max"]:
            break

    verdict = "候选待闸门3检索" if candidates else \
        "今日无Serenity信号(代码闸门层)。空手是合法输出。"
    _dump({"date": str(date.today()), "mood": mood, "hot_boards": hot,
           "calendar_gate": cal, "candidates": candidates,
           "watchlist": watchlist, "verdict": verdict, "compliance": compliance})


def _dump(payload: dict):
    out = os.path.join(ROOT, "output", f"candidates_{date.today().strftime('%Y%m%d')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"[serenity] 写出 {out} | {payload['verdict']} | 候选{len(payload['candidates'])}只")


if __name__ == "__main__":
    main()
