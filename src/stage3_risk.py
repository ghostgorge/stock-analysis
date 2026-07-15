"""阶段3(代码部分):闸门1·低风险 + 压线惩罚 + 仓位反推。
闸门3(强预期)是LLM的唯一战场——本模块只输出待检索清单,由Claude Code按CLAUDE.md协议完成。"""
from __future__ import annotations


def gate1_risk(price: float, s2_detail: dict, params: dict) -> dict:
    stop = max(s2_detail["pullback_low"], s2_detail["platform_top"])
    risk_pct = round((price - stop) / price * 100, 2)
    p = params["stage3"]
    return {
        "stop": round(stop, 2),
        "risk_pct": risk_pct,
        "gate1_pass": risk_pct <= p["max_risk_pct"] and risk_pct > 0,
        "position_pct": min(round(p["risk_budget_pct"] / max(risk_pct, 0.01) * 100, 1),
                            p["position_cap_pct"]) if risk_pct > 0 else 0.0,
    }


def borderline_check(readings: dict, params: dict) -> dict:
    """压线惩罚:关键读数落在阈值的90%~100%区间视为贴线。"""
    p3, p1, p2 = params["stage3"], params["stage1"], params["stage2"]
    band = p3["borderline_band_pct"]
    checks = {
        "dist_ma20": (readings.get("dist_ma20_pct", 0), p1["max_dist_ma20_pct"]),
        "risk_pct": (readings.get("risk_pct", 0), p3["max_risk_pct"]),
        "gain_60d": (readings.get("gain_60d_pct", 0), p1["gain_60d_max_pct"]),
        "adx": (readings.get("adx", 0), p2["adx_start_max"]),
    }
    hit = [k for k, (v, limit) in checks.items() if limit * band <= v <= limit]
    return {
        "borderline_items": hit,
        "penalty": len(hit) * p3["borderline_penalty"],
        "downgrade": len(hit) >= p3["borderline_downgrade_count"],
    }
