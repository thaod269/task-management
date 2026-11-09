"""Single-stock quality / valuation / technical screener, composite scores and buy ladder.

Honest data caveats (also surfaced in the UI):
* Yahoo exposes no *historical* analyst estimates, so valuation Z-scores are computed on
  a **trailing** multiple history (price / as-of TTM EPS, EV / as-of TTM EBITDA) rebuilt
  from the filed statements Yahoo does provide. Forward P/E and EV/NTM EBITDA are shown as
  *current* values (NTM EBITDA is a proxy: TTM EBITDA scaled by forward/trailing EPS growth).
* Yahoo returns ~4 fiscal years / ~5 quarters of statements, so the "3-year" windows are
  best-effort; ``coverage`` and ``notes`` columns say exactly what was missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import SCREENER, STOCK_META, ScreenerParams, universe_of
from data_loader import (RawFundamentals, clean_number, get_row, last_value, ttm_sum)

NAN = float("nan")

# Statement line-item aliases (Yahoo renames items between tickers/versions).
A_EBIT = ["EBIT", "Operating Income", "Total Operating Income As Reported"]
A_EBITDA = ["EBITDA", "Normalized EBITDA"]
A_DA = ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement",
        "Depreciation Amortization Depletion", "Depreciation And Amortization"]
A_TAX = ["Tax Provision", "Income Tax Expense"]
A_PRETAX = ["Pretax Income", "Income Before Tax"]
A_NI = ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"]
A_EPS = ["Diluted EPS", "Basic EPS"]
A_DEBT = ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"]
A_CASH = ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents",
          "Cash Financial"]
A_EQUITY = ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"]
A_INVCAP = ["Invested Capital"]
A_NETDEBT = ["Net Debt"]
A_CFO = ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
         "Total Cash From Operating Activities"]
A_CAPEX = ["Capital Expenditure", "Purchase Of PPE", "Capital Expenditures"]
A_SBC = ["Stock Based Compensation", "Share Based Compensation"]


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _lin(x: float, lo: float, hi: float) -> float:
    """Linear 0-1 score: lo -> 0, hi -> 1 (works for hi < lo, i.e. 'lower is better')."""
    if x is None or np.isnan(x) or hi == lo:
        return NAN
    return _clip01((x - lo) / (hi - lo))


# ---------------------------------------------------------------------------
# Technical gauges
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(~((dn == 0) & (up > 0)), 100.0)


def bollinger(close: pd.Series, window: int = 20, sigma: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    sd = close.rolling(window).std()
    return pd.DataFrame({"Mid": mid, "Upper": mid + sigma * sd, "Lower": mid - sigma * sd})


def technical_gauges(close: pd.Series, volume: pd.Series | None = None,
                     params: ScreenerParams = SCREENER) -> dict:
    close = close.dropna()
    g: dict = {"Price": NAN, "High52": NAN, "Low52": NAN, "Drawdown_%": NAN, "RSI14": NAN,
               "SMA50": NAN, "SMA200": NAN, "Dist_SMA200_%": NAN, "BB_Lower": NAN,
               "BB_Upper": NAN, "Vol_Spike_x": NAN}
    if close.empty:
        return g
    px = float(close.iloc[-1])
    yr = close.iloc[-252:]
    g["Price"], g["High52"], g["Low52"] = px, float(yr.max()), float(yr.min())
    g["Drawdown_%"] = (px / g["High52"] - 1) * 100
    r = rsi(close, params.rsi_window)
    g["RSI14"] = last_value(r.dropna())
    if len(close) >= 50:
        g["SMA50"] = float(close.rolling(50).mean().iloc[-1])
    if len(close) >= params.sma_long:
        g["SMA200"] = float(close.rolling(params.sma_long).mean().iloc[-1])
        g["Dist_SMA200_%"] = (px / g["SMA200"] - 1) * 100
    if len(close) >= 20:
        bb = bollinger(close)
        g["BB_Lower"], g["BB_Upper"] = float(bb.Lower.iloc[-1]), float(bb.Upper.iloc[-1])
    if volume is not None and volume.notna().sum() > params.vol_window + 5:
        v = volume.reindex(close.index)
        ratio = v / v.shift(1).rolling(params.vol_window).mean()
        down = close.pct_change() < 0
        spikes = ratio.where(down).tail(5).dropna()  # capitulation = heavy volume on a down day
        g["Vol_Spike_x"] = float(spikes.max()) if len(spikes) else float(ratio.tail(5).max())
    return g


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------
@dataclass
class FundamentalSnapshot:
    ticker: str
    is_financial: bool = False
    roic_3y: float = NAN
    roic_is_proxy: bool = False
    net_debt_ebitda: float = NAN
    fcf_raw: float = NAN
    sbc: float = NAN
    fcf_adj: float = NAN
    fwd_pe: float = NAN
    ev_ebitda_ttm: float = NAN
    ev_ntm_ebitda: float = NAN
    pe_z: float = NAN
    ev_z: float = NAN
    val_z: float = NAN
    val_price_m2: float = NAN        # price at which the multiple would sit 2σ below its 3y median
    revision_breadth: float = NAN    # in [-1, 1]
    notes: list[str] = field(default_factory=list)


def _roic_series(raw: RawFundamentals, tax_default: float) -> tuple[pd.Series, bool]:
    """NOPAT / invested capital per fiscal year. Financials use ROE as a documented proxy."""
    inc, bal = raw.income, raw.balance
    sector = str(raw.info.get("sector", ""))
    if sector == "Financial Services":
        ni, eq = get_row(inc, A_NI), get_row(bal, A_EQUITY)
        j = pd.concat([ni, eq], axis=1, keys=["net_income", "equity"]).dropna()
        return (j["net_income"] / j["equity"].replace(0, np.nan)).dropna(), True

    ebit, tax, pretax = get_row(inc, A_EBIT), get_row(inc, A_TAX), get_row(inc, A_PRETAX)
    rate = (tax / pretax.replace(0, np.nan)).clip(0.0, 0.35) if len(tax) and len(pretax) else pd.Series(dtype=float)
    invcap = get_row(bal, A_INVCAP)
    if invcap.empty:
        debt, eq, cash = get_row(bal, A_DEBT), get_row(bal, A_EQUITY), get_row(bal, A_CASH)
        if len(eq):
            invcap = (debt.reindex(eq.index).fillna(0) + eq - cash.reindex(eq.index).fillna(0))
    if ebit.empty or invcap.empty:
        return pd.Series(dtype=float), False

    def match(s: pd.Series, d: pd.Timestamp):  # nearest fiscal date within 45 days
        if s.empty:
            return NAN
        i = s.index.get_indexer([d], method="nearest")[0]
        return float(s.iloc[i]) if abs((s.index[i] - d).days) <= 45 else NAN

    vals = {}
    for d, e in ebit.items():
        t = match(rate, d)
        t = tax_default if np.isnan(t) else t
        ic = match(invcap, d)
        if not np.isnan(ic) and ic > 0:
            vals[d] = e * (1 - t) / ic
    return pd.Series(vals, dtype=float).sort_index(), False


def _asof_points(annual: pd.Series, quarterly: pd.Series, lag_a: int = 75, lag_q: int = 45) -> pd.Series:
    """Build an 'as-reported-by-date' TTM series: fiscal-year values and rolling-4Q sums, shifted by filing lag."""
    pts: dict[pd.Timestamp, float] = {}
    for d, v in annual.items():
        pts[d + pd.Timedelta(days=lag_a)] = v
    if len(quarterly) >= 4:
        ttm = quarterly.rolling(4).sum().dropna()
        for d, v in ttm.items():
            pts[d + pd.Timedelta(days=lag_q)] = v
    return pd.Series(pts, dtype=float).sort_index()


def _daily_asof(points: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    if points.empty:
        return pd.Series(np.nan, index=index)
    return points.reindex(points.index.union(index)).ffill().reindex(index)


def _multiple_stats(mult: pd.Series, params: ScreenerParams) -> tuple[float, float, float]:
    """Return (current, median, std) of the multiple over the lookback window (positive values only)."""
    m = mult.replace([np.inf, -np.inf], np.nan).where(mult > 0).dropna().iloc[-params.val_lookback_days:]
    if len(m) < params.val_min_obs:
        return NAN, NAN, NAN
    sd = float(m.std())
    return float(m.iloc[-1]), float(m.median()), sd if sd > 0 else NAN


def compute_fundamentals(raw: RawFundamentals, close: pd.Series,
                         params: ScreenerParams = SCREENER) -> FundamentalSnapshot:
    """Derive quality, solvency, FCF, valuation and revision metrics; never raises on missing keys."""
    snap = FundamentalSnapshot(ticker=raw.ticker, notes=list(raw.notes))
    info = raw.info or {}
    snap.is_financial = str(info.get("sector", "")) == "Financial Services"
    px = float(close.dropna().iloc[-1]) if close.notna().any() else NAN

    # ---- ROIC (3y average) ------------------------------------------------
    try:
        roic, proxy = _roic_series(raw, params.tax_rate_default)
        if len(roic):
            snap.roic_3y, snap.roic_is_proxy = float(roic.iloc[-3:].mean()), proxy
            if len(roic) < 3:
                snap.notes.append(f"ROIC averaged over {len(roic)}y (history short)")
            if proxy:
                snap.notes.append("ROIC = ROE proxy (financial company)")
        else:
            snap.notes.append("ROIC unavailable (missing EBIT/invested capital)")
    except Exception as exc:  # noqa: BLE001
        snap.notes.append(f"ROIC failed: {type(exc).__name__}")

    # ---- EBITDA (TTM) & net debt ------------------------------------------
    ebitda_a, ebitda_q = get_row(raw.income, A_EBITDA), get_row(raw.q_income, A_EBITDA)
    if ebitda_a.empty and ebitda_q.empty:  # rebuild from EBIT + D&A
        ebit_a, da_a = get_row(raw.income, A_EBIT), get_row(raw.income, A_DA)
        ebit_q, da_q = get_row(raw.q_income, A_EBIT), get_row(raw.q_income, A_DA)
        if not ebit_a.empty:
            ebitda_a = (ebit_a + da_a.reindex(ebit_a.index).fillna(0)).dropna()
        if not ebit_q.empty:
            ebitda_q = (ebit_q + da_q.reindex(ebit_q.index).fillna(0)).dropna()
    ebitda_ttm = ttm_sum(ebitda_q, ebitda_a)
    if np.isnan(ebitda_ttm):
        ebitda_ttm = clean_number(info.get("ebitda"))
    if np.isnan(ebitda_ttm):
        snap.notes.append("EBITDA unavailable")

    bal = raw.q_balance if not raw.q_balance.empty else raw.balance
    nd = last_value(get_row(bal, A_NETDEBT))
    if np.isnan(nd):
        debt, cash = last_value(get_row(bal, A_DEBT)), last_value(get_row(bal, A_CASH))
        if not np.isnan(debt):
            nd = debt - (0.0 if np.isnan(cash) else cash)
    if np.isnan(nd):
        nd = clean_number(info.get("totalDebt")) - clean_number(info.get("totalCash"), 0.0)
    if snap.is_financial:
        snap.notes.append("Net debt/EBITDA not meaningful for financials (neutral)")
    elif not np.isnan(nd) and not np.isnan(ebitda_ttm):
        snap.net_debt_ebitda = nd / ebitda_ttm if ebitda_ttm > 0 else (np.inf if nd > 0 else NAN)
    else:
        snap.notes.append("Net debt/EBITDA unavailable")

    # ---- Dilution-adjusted FCF = CFO - CapEx - SBC -------------------------
    cfo = ttm_sum(get_row(raw.q_cashflow, A_CFO), get_row(raw.cashflow, A_CFO))
    capex = ttm_sum(get_row(raw.q_cashflow, A_CAPEX), get_row(raw.cashflow, A_CAPEX))
    sbc = ttm_sum(get_row(raw.q_cashflow, A_SBC), get_row(raw.cashflow, A_SBC))
    if np.isnan(cfo):
        snap.notes.append("Operating cash flow unavailable")
    else:
        if np.isnan(capex):
            snap.notes.append("CapEx missing - FCF may be overstated")
        capex = 0.0 if np.isnan(capex) else -abs(capex)
        if np.isnan(sbc):
            snap.notes.append("SBC missing - FCF not dilution-adjusted")
        snap.sbc = sbc
        snap.fcf_raw = cfo + capex
        snap.fcf_adj = snap.fcf_raw - (0.0 if np.isnan(sbc) else sbc)

    # ---- Current forward multiples ------------------------------------------
    snap.fwd_pe = clean_number(info.get("forwardPE"))
    ev_now = clean_number(info.get("enterpriseValue"))
    shares = clean_number(info.get("sharesOutstanding"))
    if np.isnan(shares) and not np.isnan(clean_number(info.get("marketCap"))) and px:
        shares = info["marketCap"] / px
    if np.isnan(ev_now) and not np.isnan(shares) and not np.isnan(nd) and not np.isnan(px):
        ev_now = shares * px + nd
    if not np.isnan(ev_now) and not np.isnan(ebitda_ttm) and ebitda_ttm > 0:
        snap.ev_ebitda_ttm = ev_now / ebitda_ttm
        f_eps, t_eps = clean_number(info.get("forwardEps")), clean_number(info.get("trailingEps"))
        growth = float(np.clip(f_eps / t_eps, 0.7, 1.6)) if f_eps > 0 and t_eps > 0 else 1.0
        snap.ev_ntm_ebitda = ev_now / (ebitda_ttm * growth)

    # ---- Valuation history z-scores (trailing basis) -------------------------
    c = close.dropna()
    if len(c) >= params.val_min_obs:
        idx = c.index
        eps_pts = _asof_points(get_row(raw.income, A_EPS), get_row(raw.q_income, A_EPS))
        pe_cur, pe_med, pe_sd = _multiple_stats(c / _daily_asof(eps_pts, idx), params)
        if not np.isnan(pe_sd):
            snap.pe_z = (pe_cur - pe_med) / pe_sd
            snap.val_price_m2 = px * (pe_med - 2 * pe_sd) / pe_cur  # EPS held constant
        ebitda_pts = _asof_points(ebitda_a, ebitda_q)
        if not np.isnan(shares) and not np.isnan(nd) and len(ebitda_pts):
            ev_hist = c * shares + nd
            ev_cur, ev_med, ev_sd = _multiple_stats(ev_hist / _daily_asof(ebitda_pts, idx), params)
            if not np.isnan(ev_sd):
                snap.ev_z = (ev_cur - ev_med) / ev_sd
                if np.isnan(snap.val_price_m2) and ebitda_ttm > 0:
                    snap.val_price_m2 = ((ev_med - 2 * ev_sd) * ebitda_ttm - nd) / shares
    zs = [z for z in (snap.pe_z, snap.ev_z) if not np.isnan(z)]
    if zs:
        snap.val_z = float(np.mean(zs))
    else:
        snap.notes.append("Valuation z-score unavailable (insufficient EPS/EBITDA history)")

    # ---- Earnings revision breadth ------------------------------------------
    snap.revision_breadth = _revision_breadth(raw.eps_revisions)
    if np.isnan(snap.revision_breadth):
        snap.notes.append("EPS revision breadth unavailable")
    return snap


def _revision_breadth(df: pd.DataFrame) -> float:
    """(up - down) / (up + down) over the last 30 days across forecast periods, in [-1, 1]."""
    if df is None or df.empty:
        return NAN
    cols = {str(c).lower(): c for c in df.columns}
    up, dn = cols.get("uplast30days"), cols.get("downlast30days")
    if up is None or dn is None:
        return NAN
    u = pd.to_numeric(df[up], errors="coerce").fillna(0).sum()
    d = pd.to_numeric(df[dn], errors="coerce").fillna(0).sum()
    return float((u - d) / (u + d)) if (u + d) > 0 else 0.0


# ---------------------------------------------------------------------------
# Composite scores
# ---------------------------------------------------------------------------
@dataclass
class ScoreResult:
    score: float
    coverage: float                     # share of weight backed by real data (0-1)
    components: dict[str, float]


def _combine(parts: dict[str, tuple[float, float]]) -> ScoreResult:
    """parts: name -> (0..1 score or NaN, weight). Missing parts are dropped and weights renormalised."""
    have = {k: (s, w) for k, (s, w) in parts.items() if s is not None and not np.isnan(s)}
    tot = sum(w for _, w in parts.values())
    wsum = sum(w for _, w in have.values())
    if wsum == 0:
        return ScoreResult(NAN, 0.0, {})
    score = 100 * sum(s * w for s, w in have.values()) / wsum
    return ScoreResult(score, wsum / tot, {k: 100 * s for k, (s, _) in have.items()})


def technical_capitulation_score(g: dict) -> float:
    """0-1 average of RSI, drawdown, distance-to-200SMA and volume-spike sub-scores."""
    subs = [
        (_lin(g["RSI14"], 50, 25), 0.30),
        (_lin(-g["Drawdown_%"] if not np.isnan(g["Drawdown_%"]) else NAN, 5, 35), 0.30),
        (_lin(g["Dist_SMA200_%"], 10, -15), 0.20),
        (_lin(g["Vol_Spike_x"], 1.0, 3.0), 0.20),
    ]
    have = [(s, w) for s, w in subs if not np.isnan(s)]
    return sum(s * w for s, w in have) / sum(w for _, w in have) if have else NAN


def _solvency_score(f: "FundamentalSnapshot", cap: float) -> float:
    """0-1: net cash -> 1.0, exactly at the leverage cap -> 0.5, 2x the cap or worse -> 0."""
    if f.is_financial:
        return 0.5  # leverage metrics are not comparable for banks/insurers -> neutral
    nd = f.net_debt_ebitda
    if np.isnan(nd):
        return NAN
    if np.isinf(nd) or nd >= 2 * cap:
        return 0.0
    if nd <= 0:
        return 1.0
    if nd <= cap:
        return 1.0 - 0.5 * nd / cap
    return 0.5 * (2 * cap - nd) / cap


def tech_dip_conviction(g: dict, f: FundamentalSnapshot, universe: str,
                        params: ScreenerParams = SCREENER) -> ScoreResult:
    thr = params.roic_min.get(universe, 0.10)
    w = params.dip_weights
    solvency = _solvency_score(f, params.nd_ebitda_max)
    parts = {
        "roic": (_lin(f.roic_3y, 0.5 * thr, 2 * thr), w["roic"]),
        "solvency": (solvency, w["solvency"]),
        "fcf": (NAN if np.isnan(f.fcf_adj) else (1.0 if f.fcf_adj > 0 else 0.0), w["fcf"]),
        "valuation": (_lin(f.val_z, 1.0, params.val_extreme_z), w["valuation"]),
        "technical": (technical_capitulation_score(g), w["technical"]),
    }
    return _combine(parts)


def rotation_absorption(rs_roc20: float, sector_momentum: float, f: FundamentalSnapshot,
                        params: ScreenerParams = SCREENER) -> ScoreResult:
    """Gaining RS momentum vs SPY + positive revision breadth + low EV/EBITDA."""
    w = params.absorb_weights
    rs_stock = _lin(rs_roc20, -0.05, 0.05)
    rs_sector = _lin(sector_momentum, 98.0, 102.0)
    rs_parts = [s for s in (rs_stock, rs_sector) if not np.isnan(s)]
    multiple = f.ev_ntm_ebitda if not np.isnan(f.ev_ntm_ebitda) else f.ev_ebitda_ttm
    parts = {
        "rs_momentum": (float(np.mean(rs_parts)) if rs_parts else NAN, w["rs_momentum"]),
        "revisions": (_lin(f.revision_breadth, -1, 1), w["revisions"]),
        "cheapness": (_lin(multiple, 25.0, 8.0), w["cheapness"]),
    }
    return _combine(parts)


# ---------------------------------------------------------------------------
# Universe screen
# ---------------------------------------------------------------------------
def screen_universe(prices: pd.DataFrame, volume: pd.DataFrame,
                    raw: dict[str, RawFundamentals], rrg: pd.DataFrame | None = None,
                    tickers: list[str] | None = None, bench: str = "SPY",
                    params: ScreenerParams = SCREENER) -> pd.DataFrame:
    tickers = [t for t in (tickers or list(STOCK_META)) if t in prices.columns]
    rows = []
    for t in tickers:
        universe, sector, sector_etf = STOCK_META[t]
        close = prices[t].dropna()
        g = technical_gauges(close, volume[t] if t in volume.columns else None, params)
        f = compute_fundamentals(raw.get(t, RawFundamentals(ticker=t, notes=["fundamentals not loaded"])),
                                 close, params)

        rs_roc = NAN
        if bench in prices.columns:
            ratio = (prices[t] / prices[bench]).dropna()
            if len(ratio) > 21:
                rs_roc = float(ratio.iloc[-1] / ratio.iloc[-21] - 1)
        sector_mom = float(rrg.loc[sector_etf, "RS_Momentum"]) if rrg is not None and sector_etf in rrg.index else NAN
        sector_quad = str(rrg.loc[sector_etf, "Quadrant"]) if rrg is not None and sector_etf in rrg.index else "n/a"

        dip = tech_dip_conviction(g, f, universe, params)
        ab = rotation_absorption(rs_roc, sector_mom, f, params)

        thr = params.roic_min[universe]
        solv_ok = True if f.is_financial else (f.net_debt_ebitda <= params.nd_ebitda_max if not np.isnan(f.net_debt_ebitda) else None)
        roic_ok = None if np.isnan(f.roic_3y) else f.roic_3y >= thr
        fcf_ok = None if np.isnan(f.fcf_adj) else f.fcf_adj > 0
        gates = [roic_ok, solv_ok, fcf_ok]
        quality_pass = all(x is True for x in gates)
        oversold = bool(g["RSI14"] < params.rsi_oversold) if not np.isnan(g["RSI14"]) else False
        score = dip.score
        if np.isnan(score):
            signal = "No data"
        elif score >= params.strong_signal_score and quality_pass and oversold:
            signal = "STRONG DIP BUY"
        elif score >= params.watch_signal_score and not any(x is False for x in gates):
            signal = "Watchlist"
        else:
            signal = "No signal"

        rows.append({
            "Ticker": t, "Universe": universe, "Sector": sector, "Sector ETF": sector_etf,
            "Sector Quadrant": sector_quad,
            "Price": g["Price"], "RSI": g["RSI14"], "Drawdown %": g["Drawdown_%"],
            "Dist SMA200 %": g["Dist_SMA200_%"], "Vol Spike x": g["Vol_Spike_x"],
            "ROIC % (3y)": f.roic_3y * 100 if not np.isnan(f.roic_3y) else NAN,
            "ND/EBITDA": f.net_debt_ebitda, "FCF adj ($B)": f.fcf_adj / 1e9 if not np.isnan(f.fcf_adj) else NAN,
            "Fwd P/E": f.fwd_pe, "EV/NTM EBITDA": f.ev_ntm_ebitda,
            "Valuation Z": f.val_z, "Rev Breadth": f.revision_breadth,
            "RS ROC20 %": rs_roc * 100 if not np.isnan(rs_roc) else NAN,
            "Dip Score": dip.score, "Dip Coverage": dip.coverage,
            "Absorb Score": ab.score, "Absorb Coverage": ab.coverage,
            "Quality Pass": quality_pass, "Oversold": oversold, "Signal": signal,
            "SMA200": g["SMA200"], "BB Lower": g["BB_Lower"], "Low52": g["Low52"],
            "Val Price -2σ": f.val_price_m2,
            "Notes": "; ".join(dict.fromkeys(f.notes)),
        })
    df = pd.DataFrame(rows)
    return df.set_index("Ticker") if not df.empty else df


# ---------------------------------------------------------------------------
# Buy-the-dip ladder & position sizing
# ---------------------------------------------------------------------------
def allocate_budget(scores: pd.Series, budget: float, max_weight: float = 0.35) -> pd.Series:
    """Score-proportional allocation with a per-name cap (iterative water-filling)."""
    s = scores.dropna().clip(lower=0)
    if s.empty or s.sum() == 0 or budget <= 0:
        return pd.Series(0.0, index=scores.index)
    w = pd.Series(0.0, index=s.index)
    free = pd.Series(True, index=s.index)
    remaining = 1.0
    for _ in range(len(s)):
        base = s[free] / s[free].sum() * remaining
        over = base > max_weight
        if not over.any():
            w[free] = base
            break
        w[base[over].index] = max_weight
        free[base[over].index] = False
        remaining = 1.0 - w[~free].sum()
        if not free.any():
            break
    return (w * budget).reindex(scores.index).fillna(0.0)


def build_ladder(row: pd.Series, budget: float,
                 weights: tuple[float, float, float] = SCREENER.tranche_weights) -> pd.DataFrame:
    """3-tranche limit-order ladder.

    1. Pilot (30%)       : last price less a 0.5% limit cushion.
    2. Core support (40%): highest support (200SMA, lower Bollinger Band, 52w low x1.05) that is
                           >=4% under the pilot; fallback pilot x 0.90.
    3. Deep value (30%)  : price implying the valuation multiple at 2σ below its 3y median
                           (EPS/EBITDA held constant), floored at 70% of spot and kept >=5% under
                           the core tranche; fallback core x 0.90.
    """
    px = float(row["Price"])
    pilot = px * 0.995
    cands = [row.get("SMA200"), row.get("BB Lower"),
             row.get("Low52") * 1.05 if pd.notna(row.get("Low52")) else NAN]
    cands = [float(c) for c in cands if pd.notna(c) and c <= pilot * 0.96 and c > 0]
    core = max(cands) if cands else pilot * 0.90
    core_src = "support (200SMA / BB / 52w low)" if cands else "pilot -10% (no support below)"

    val = row.get("Val Price -2σ")
    if pd.notna(val) and val > 0:
        deep = float(min(max(val, 0.70 * px), core * 0.95))
        deep_src = "valuation -2σ vs 3y median, floored/ordered"
    else:
        deep, deep_src = core * 0.90, "core -10% (no valuation history)"

    levels = [("1 - Pilot", pilot, "last price, 0.5% cushion"),
              ("2 - Core support", core, core_src),
              ("3 - Deep value (margin of safety)", deep, deep_src)]
    rows, spent, shares_tot = [], 0.0, 0
    for (name, price, basis), w in zip(levels, weights):
        alloc = budget * w
        shares = int(np.floor(alloc / price)) if price > 0 else 0
        cost = shares * price
        spent += cost
        shares_tot += shares
        rows.append({"Tranche": name, "Weight": w, "Limit Price": price,
                     "vs Spot %": (price / px - 1) * 100, "Budget $": alloc,
                     "Shares": shares, "Cost $": cost, "Basis": basis})
    df = pd.DataFrame(rows)
    df.attrs["avg_cost"] = spent / shares_tot if shares_tot else NAN
    df.attrs["total_cost"] = spent
    df.attrs["total_shares"] = shares_tot
    return df
