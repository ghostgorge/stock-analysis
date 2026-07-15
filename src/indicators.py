"""纯pandas技术指标。输入统一为日线DataFrame:
columns = [date, open, high, low, close, volume, amount], date升序。"""
import pandas as pd
import numpy as np


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist


def adx(df: pd.DataFrame, n=14):
    """Wilder ADX。返回(adx, pdi, mdi)。"""
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def gmma(close: pd.Series):
    """顾比均线。返回(短期组df, 长期组df, 长期组离散度%序列)。"""
    short = pd.DataFrame({f"e{n}": close.ewm(span=n, adjust=False).mean() for n in (3, 5, 8, 10, 12, 15)})
    long = pd.DataFrame({f"e{n}": close.ewm(span=n, adjust=False).mean() for n in (30, 35, 40, 45, 50, 60)})
    spread = (long.max(axis=1) - long.min(axis=1)) / long.mean(axis=1) * 100
    return short, long, spread


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """在原df上追加全部标准列,stage1/stage2共用。"""
    df = df.copy()
    for n in (5, 10, 20, 30, 60):
        df[f"ma{n}"] = ma(df["close"], n)
    df["vol_ma20"] = ma(df["volume"], 20)
    df["dif"], df["dea"], df["macd_hist"] = macd(df["close"])
    df["adx"], df["pdi"], df["mdi"] = adx(df)
    _, _, df["gmma_spread"] = gmma(df["close"])
    df["pct_chg"] = df["close"].pct_change() * 100
    return df
