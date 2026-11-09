"""Sector-rotation analytics: relative strength, RRG, pair spreads, regime and model portfolio.

Pure pandas/numpy - no network or UI imports - so every function is unit-testable.
``prices`` is always a DataFrame of adjusted closes (columns = tickers).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import (BENCHMARK, ETF_NAMES, ETF_STYLE, GROWTH_ETFS, ROTATION, SLEEVE_MEMBERS,
                    SLEEVE_TARGETS, RotationParams)

QUADRANTS = ("Leading", "Weakening", "Lagging", "Improving")


# ---------------------------------------------------------------------------
# Relative strength
# ---------------------------------------------------------------------------
def relative_strength_series(prices: pd.DataFrame, ticker: str, bench: str = BENCHMARK) -> pd.Series:
    """Price(ticker) / Price(benchmark)."""
    return (prices[ticker] / prices[bench]).dropna()


def relative_strength_table(prices: pd.DataFrame, etfs: list[str], bench: str = BENCHMARK,
                            params: RotationParams = ROTATION) -> pd.DataFrame:
    """RS ratio level, relative-return over each window and momentum acceleration.

    * ``RS_{w}d``  : ratio_t / ratio_{t-w} - 1 for w in 20/60/252 (outperformance vs SPY).
    * ``RS_ROC20`` : 20-day rate of change of the ratio (same as RS_20d, kept as the momentum base).
    * ``RS_Accel`` : ROC20 today minus ROC20 ten sessions ago (positive = momentum accelerating).
    """
    rows = []
    for t in etfs:
        if t not in prices.columns or bench not in prices.columns or t == bench:
            continue
        rs = relative_strength_series(prices, t, bench)
        if len(rs) < params.roc_window + 11:
            continue
        row = {"Ticker": t, "Name": ETF_NAMES.get(t, t), "Style": ETF_STYLE.get(t, ""), "RS": rs.iloc[-1]}
        for w in params.rs_windows:
            row[f"RS_{w}d"] = rs.iloc[-1] / rs.iloc[-1 - w] - 1 if len(rs) > w else np.nan
        roc = rs.pct_change(params.roc_window)
        row["RS_ROC20"] = roc.iloc[-1]
        row["RS_Accel"] = roc.iloc[-1] - roc.iloc[-11] if len(roc.dropna()) > 10 else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("Ticker") if rows else pd.DataFrame()


def money_flow_proxy(prices: pd.DataFrame, volume: pd.DataFrame, etfs: list[str],
                     window: int = ROTATION.flow_window) -> pd.Series:
    """Signed dollar-volume flow in [-1, 1] over ``window`` days.

    sum(sign(return) * price * volume) / sum(price * volume). A *proxy* for net
    buying pressure (true ETF creations/redemptions are not available from Yahoo).
    """
    out = {}
    for t in etfs:
        if t not in prices.columns or t not in volume.columns:
            continue
        px, v = prices[t], volume[t]
        dv = (px * v).replace(0, np.nan)
        signed = np.sign(px.pct_change()) * dv
        den = dv.rolling(window).sum().iloc[-1]
        out[t] = signed.rolling(window).sum().iloc[-1] / den if den and not np.isnan(den) else np.nan
    return pd.Series(out, name="Flow20")


# ---------------------------------------------------------------------------
# Relative Rotation Graph
# ---------------------------------------------------------------------------
def classify_quadrant(rs_ratio: float, rs_mom: float, center: float = 100.0) -> str:
    if np.isnan(rs_ratio) or np.isnan(rs_mom):
        return "n/a"
    if rs_ratio >= center:
        return "Leading" if rs_mom >= center else "Weakening"
    return "Improving" if rs_mom >= center else "Lagging"


def rrg_series(prices: pd.DataFrame, ticker: str, bench: str = BENCHMARK,
               params: RotationParams = ROTATION) -> pd.DataFrame:
    """Full RS-Ratio / RS-Momentum history for one ticker (both centred on 100)."""
    rs = relative_strength_series(prices, ticker, bench)
    rs_ratio = 100 * rs / rs.rolling(params.rrg_norm_window).mean()
    rs_mom = 100 + 100 * rs_ratio.pct_change(params.rrg_mom_window)
    return pd.DataFrame({"RS_Ratio": rs_ratio, "RS_Momentum": rs_mom}).dropna()


def rrg_coordinates(prices: pd.DataFrame, etfs: list[str], bench: str = BENCHMARK,
                    params: RotationParams = ROTATION) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Latest RRG coordinates + quadrant for each ETF, and weekly 'tail' histories."""
    rows, tails = [], {}
    for t in etfs:
        if t == bench or t not in prices.columns or bench not in prices.columns:
            continue
        hist = rrg_series(prices, t, bench, params)
        if hist.empty:
            continue
        last = hist.iloc[-1]
        rows.append({
            "Ticker": t, "Name": ETF_NAMES.get(t, t), "Style": ETF_STYLE.get(t, ""),
            "RS_Ratio": last.RS_Ratio, "RS_Momentum": last.RS_Momentum,
            "Quadrant": classify_quadrant(last.RS_Ratio, last.RS_Momentum),
        })
        # weekly samples ending today (so the tail always terminates at the latest bar)
        tails[t] = hist.iloc[::-5].iloc[: params.rrg_tail + 1].iloc[::-1]
    df = pd.DataFrame(rows).set_index("Ticker") if rows else pd.DataFrame(
        columns=["Name", "Style", "RS_Ratio", "RS_Momentum", "Quadrant"])
    return df, tails


# ---------------------------------------------------------------------------
# Tech-to-Value pair spreads
# ---------------------------------------------------------------------------
def pair_spread(prices: pd.DataFrame, num: str, den: str, params: RotationParams = ROTATION) -> pd.DataFrame:
    """Ratio with 50/200-day SMAs and Bollinger Bands (20d, +/-2 sigma) on the ratio."""
    ratio = (prices[num] / prices[den]).dropna()
    df = pd.DataFrame({"Ratio": ratio})
    df["SMA50"] = ratio.rolling(params.pair_fast_ma).mean()
    df["SMA200"] = ratio.rolling(params.pair_slow_ma).mean()
    mid = ratio.rolling(params.bb_window).mean()
    sd = ratio.rolling(params.bb_window).std()
    df["BB_Mid"], df["BB_Up"], df["BB_Lo"] = mid, mid + params.bb_sigma * sd, mid - params.bb_sigma * sd
    df["BB_Z"] = (ratio - mid) / sd.replace(0, np.nan)
    return df


def pair_spreads(prices: pd.DataFrame, pairs: list[tuple[str, str]],
                 params: RotationParams = ROTATION) -> dict[str, pd.DataFrame]:
    return {f"{n}/{d}": pair_spread(prices, n, d, params)
            for n, d in pairs if n in prices.columns and d in prices.columns}


def pair_signals(spreads: dict[str, pd.DataFrame], params: RotationParams = ROTATION) -> pd.DataFrame:
    """Flag pairs below their 50DMA or breaking the -2 sigma Bollinger Band."""
    rows = []
    for name, df in spreads.items():
        last = df.dropna(subset=["SMA50", "BB_Lo"]).tail(1)
        if last.empty:
            continue
        r = last.iloc[0]
        below50 = bool(r.Ratio < r.SMA50)
        break2 = bool(r.Ratio < r.BB_Lo)
        state = ("SEVERE ROTATION" if below50 and break2 else
                 "ACTIVE ROTATION" if below50 or break2 else "Tech leading")
        rows.append({
            "Pair": name, "Ratio": r.Ratio, "SMA50": r.SMA50, "SMA200": r.SMA200,
            "vs_SMA50_%": (r.Ratio / r.SMA50 - 1) * 100,
            "vs_SMA200_%": (r.Ratio / r.SMA200 - 1) * 100 if pd.notna(r.SMA200) else np.nan,
            "BB_Z": r.BB_Z, "Below_50DMA": below50, "Break_-2σ": break2, "State": state,
        })
    return pd.DataFrame(rows).set_index("Pair") if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------
@dataclass
class RegimeResult:
    severity: int                      # 0 intact, 1 early warning, 2 active, 3 severe
    label: str
    headline: str
    detail: str
    tech_outflows: list[str] = field(default_factory=list)
    inflows: list[str] = field(default_factory=list)
    flagged_pairs: list[str] = field(default_factory=list)


_LABELS = {
    0: "Tech Leadership Intact",
    1: "Early Warning: Isolated Tech-vs-Value Weakness",
    2: "Active Tech-to-Value Rotation Regime",
    3: "Severe Tech-to-Value Rotation Regime",
}


def rotation_havens(rrg: pd.DataFrame, rs_table: pd.DataFrame | None = None,
                    exclude_growth: bool = True, top_n: int = 3) -> pd.DataFrame:
    """Rank non-growth ETFs absorbing liquidity: Leading/Improving first, then RS-momentum."""
    if rrg.empty:
        return rrg
    df = rrg.copy()
    if exclude_growth:
        df = df[~df.index.isin(GROWTH_ETFS)]
    if rs_table is not None and not rs_table.empty:
        df = df.join(rs_table[["RS_ROC20", "RS_Accel"]], how="left")
    df["Absorbing"] = df["Quadrant"].isin(["Leading", "Improving"])
    df["_rank"] = df["RS_Momentum"] + (df["RS_Ratio"] - 100) * 0.5
    df = df.sort_values(["Absorbing", "_rank"], ascending=[False, False]).drop(columns="_rank")
    return df.head(top_n) if top_n else df


def detect_regime(signals: pd.DataFrame, rrg: pd.DataFrame, rs_table: pd.DataFrame | None = None,
                  min_pairs_active: int = 2) -> RegimeResult:
    """Combine pair-spread flags with RRG positions into a single market-regime read."""
    n_flag = int((signals["State"] != "Tech leading").sum()) if not signals.empty else 0
    n_sev = int((signals["State"] == "SEVERE ROTATION").sum()) if not signals.empty else 0
    n_pairs = len(signals)

    if n_flag == 0:
        severity = 0
    elif n_flag < min_pairs_active:
        severity = 1
    elif n_flag >= max(3, min_pairs_active + 1) and n_sev >= 1:
        severity = 3
    else:
        severity = 2

    growth = rrg[rrg.index.isin(GROWTH_ETFS)] if not rrg.empty else rrg
    outflows = list(growth[growth["Quadrant"].isin(["Weakening", "Lagging"])].index) if not growth.empty else []
    havens = rotation_havens(rrg, rs_table, top_n=3)
    inflows = [t for t in havens.index if havens.loc[t, "Absorbing"]] if not havens.empty else []
    flagged = list(signals.index[signals["State"] != "Tech leading"]) if not signals.empty else []

    def names(ts: list[str]) -> str:
        return " / ".join(ETF_NAMES.get(t, t) for t in ts) or "no clear destination"

    if severity == 0:
        leaders = list(growth[growth["Quadrant"].isin(["Leading", "Improving"])].index) if not growth.empty else []
        headline = "No Rotation: Tech/Growth leadership intact" + (f" ({', '.join(leaders)})" if leaders else "")
        detail = f"0 of {n_pairs} tech-vs-value pair spreads are below their 50DMA or -2σ band."
    else:
        prefix = {1: "Early Warning", 2: "Active Rotation", 3: "Severe Rotation"}[severity]
        out_txt = ", ".join(outflows) if outflows else "relative weakness in tech pairs"
        headline = f"{prefix}: Tech Outflows ({out_txt}) → {names(inflows)} Inflows"
        detail = (f"{n_flag} of {n_pairs} pair spreads flagged ({', '.join(flagged)}); "
                  f"{n_sev} below both 50DMA and -2σ band.")
    return RegimeResult(severity, _LABELS[severity], headline, detail, outflows, inflows, flagged)


# ---------------------------------------------------------------------------
# Model portfolio (Tab 3)
# ---------------------------------------------------------------------------
def _tilted_weights(base: dict[str, float], momentum: pd.Series | None, tilt: float = 0.25) -> dict[str, float]:
    """Bounded momentum tilt inside a sleeve: w_i ~ base_i * exp(tilt * z_i), z clipped to +/-2."""
    w = pd.Series(base, dtype=float)
    if momentum is not None and len(w) > 1:
        m = momentum.reindex(w.index)
        if m.notna().sum() > 1 and m.std(ddof=0) > 0:
            z = ((m - m.mean()) / m.std(ddof=0)).fillna(0).clip(-2, 2)
            w = w * np.exp(tilt * z)
    return (w / w.sum()).to_dict()


def build_model_portfolio(severity: int, rrg: pd.DataFrame | None, last_prices: pd.Series | None,
                          budget: float, include_defensive: bool = True, tilt: float = 0.25,
                          current_values: dict[str, float] | None = None) -> pd.DataFrame:
    """Rotation-aware ETF allocation between Growth (QQQ/XLK), Value (RSP/XLF/XLI) and Defensive sleeves."""
    sleeve_w = dict(zip(("Growth", "Value", "Defensive"), SLEEVE_TARGETS[int(np.clip(severity, 0, 3))]))
    if not include_defensive:
        sleeve_w["Value"] += sleeve_w.pop("Defensive")
        sleeve_w["Defensive"] = 0.0
    momentum = rrg["RS_Momentum"] if rrg is not None and not rrg.empty else None

    rows = []
    for sleeve, members in SLEEVE_MEMBERS.items():
        if sleeve_w.get(sleeve, 0) <= 0:
            continue
        for t, w in _tilted_weights(members, momentum, tilt).items():
            rows.append({"Ticker": t, "Name": ETF_NAMES.get(t, t), "Sleeve": sleeve,
                         "Target_Weight": sleeve_w[sleeve] * w})
    df = pd.DataFrame(rows)
    df["Target_$"] = df["Target_Weight"] * budget
    if last_prices is not None:
        df["Price"] = df["Ticker"].map(last_prices)
        df["Target_Shares"] = np.floor(df["Target_$"] / df["Price"]).astype("Int64")
    if current_values is not None:
        df["Current_$"] = df["Ticker"].map(current_values).fillna(0.0)
        df["Trade_$"] = df["Target_$"] - df["Current_$"]
        df["Action"] = np.where(df["Trade_$"].abs() < 0.005 * budget, "Hold",
                                np.where(df["Trade_$"] > 0, "Buy", "Trim"))
    return df.set_index("Ticker")
