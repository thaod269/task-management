"""Deterministic *synthetic* market + fundamentals data.

Used when Yahoo Finance is unreachable (offline / rate-limited) and by the test-suite.
These numbers are NOT real market data - the UI labels demo mode prominently.
Statement frames mimic yfinance's shape (line items as rows, period-end dates as columns,
newest first) so the exact same engine code path is exercised.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import ALL_ETFS, ALL_STOCKS, BENCHMARK, STOCK_META
from data_loader import MarketData, RawFundamentals

# annual drift / vol assumptions (rough, illustrative)
_DRIFT = {"XLK": .16, "SMH": .22, "XLC": .12, "QQQ": .15, "XLF": .10, "XLI": .10, "XLE": .06,
          "RSP": .08, "SCHD": .07, "XLV": .06, "XLU": .05, "XLP": .05, "XLY": .11, "XLRE": .04,
          "XLB": .07, "SPY": .10}
_VOL = {"SMH": .32, "XLK": .24, "QQQ": .22, "XLE": .26, "XLC": .22}


def make_market_data(n_days: int = 1000, seed: int = 7, rotation: bool = True) -> MarketData:
    """Correlated GBM paths; with ``rotation`` the last ~45 sessions bleed tech into value/defensives."""
    rng = np.random.default_rng(seed)
    tickers = ALL_ETFS + ALL_STOCKS
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    mkt = rng.normal(0.10 / 252, 0.011, n_days)
    growth_factor = rng.normal(0, 0.007, n_days)
    prices, vols = {}, {}
    for t in tickers:
        is_growth = t in ("XLK", "SMH", "XLC", "QQQ") or (t in STOCK_META and STOCK_META[t][0] == "Tech/AI")
        mu = _DRIFT.get(t, 0.12 if is_growth else 0.08) / 252
        sig = _VOL.get(t, 0.30 if t in STOCK_META else 0.16) / np.sqrt(252)
        beta_g = 1.0 if is_growth else -0.1
        ret = mu + 0.8 * mkt + beta_g * growth_factor + rng.normal(0, sig * 0.6, n_days)
        if rotation:
            k = 45
            if is_growth:
                ret[-k:] += np.linspace(-0.0035, -0.0015, k) * (1.6 if t in STOCK_META else 1.0)
            elif t in ("XLF", "XLI", "XLE", "RSP", "SCHD", "CAT", "GE", "JPM", "BRK.B"):
                ret[-k:] += 0.0015
        base = rng.uniform(40, 400)
        p = base * np.exp(np.cumsum(ret))
        prices[t] = p
        v = rng.lognormal(mean=np.log(5e6 if t in STOCK_META else 2e7), sigma=0.25, size=n_days)
        down = np.r_[False, np.diff(p) < 0]
        v[-4:] *= np.where(down[-4:], 2.5, 1.0) if t in STOCK_META else 1.0  # capitulation-like prints
        vols[t] = v
    return MarketData(prices=pd.DataFrame(prices, index=idx), volume=pd.DataFrame(vols, index=idx),
                      warnings=["DEMO MODE: synthetic data, not real market prices."], source="demo")


def _stmt(rows: dict[str, list[float]], dates: list[pd.Timestamp]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=dates).T


def make_raw_fundamentals(prices: pd.DataFrame, seed: int = 11) -> dict[str, RawFundamentals]:
    """Yahoo-shaped statements; one ticker deliberately lacks SBC / EPS revisions to test degradation."""
    rng = np.random.default_rng(seed)
    out: dict[str, RawFundamentals] = {}
    today = prices.index[-1]
    a_dates = [today - pd.DateOffset(months=3 + 12 * i) for i in range(4)]   # newest first
    q_dates = [today - pd.DateOffset(months=3 * (i + 1)) for i in range(5)]
    for t in ALL_STOCKS:
        universe, sector, _ = STOCK_META[t]
        tech = universe == "Tech/AI"
        fin = t in ("JPM", "BRK.B")
        px = float(prices[t].iloc[-1])
        shares = float(rng.uniform(1e9, 8e9))
        rev0 = px * shares / (rng.uniform(4, 9) if tech else rng.uniform(1.5, 3.5))
        grow = 1.12 if tech else 1.05
        rev_a = [rev0 / grow ** i for i in range(4)]
        margin = rng.uniform(0.28, 0.45) if tech else rng.uniform(0.15, 0.25)
        ebit_a = [r * margin for r in rev_a]
        da_a = [r * 0.05 for r in rev_a]
        ni_a = [e * 0.8 for e in ebit_a]
        eps_a = [n / shares for n in ni_a]
        eq = rev0 * rng.uniform(0.6, 1.0)
        debt = eq * (rng.uniform(0.05, 0.4) if tech else rng.uniform(0.3, 0.8))
        cash = eq * rng.uniform(0.2, 0.5)
        income = _stmt({"EBIT": ebit_a, "EBITDA": [e + d for e, d in zip(ebit_a, da_a)],
                        "Tax Provision": [e * .18 for e in ebit_a], "Pretax Income": ebit_a,
                        "Net Income": ni_a, "Diluted EPS": eps_a}, a_dates)
        q_scale = np.array([1, .98, .96, .94, .92])
        q_ebit = ebit_a[0] / 4 * q_scale
        q_income = _stmt({"EBIT": list(q_ebit), "EBITDA": list(q_ebit * 1.15),
                          "Diluted EPS": list(eps_a[0] / 4 * q_scale)}, q_dates)
        balance = _stmt({"Total Debt": [debt * (1 - .05 * i) for i in range(4)],
                         "Stockholders Equity": [eq / (1.08 ** i) for i in range(4)],
                         "Cash Cash Equivalents And Short Term Investments": [cash] * 4}, a_dates)
        q_balance = _stmt({"Total Debt": [debt] * 5, "Net Debt": [debt - cash] * 5,
                           "Stockholders Equity": [eq] * 5}, q_dates)
        cfo = ebit_a[0] * 1.1
        cf_rows = {"Operating Cash Flow": [cfo / 4] * 5, "Capital Expenditure": [-cfo / 12] * 5,
                   "Stock Based Compensation": [cfo / 20] * 5}
        q_cashflow = _stmt(cf_rows, q_dates)
        cashflow = _stmt({"Operating Cash Flow": [cfo] * 4, "Capital Expenditure": [-cfo / 3] * 4,
                          "Stock Based Compensation": [cfo / 5] * 4}, a_dates)
        up, dn = int(rng.integers(0, 12)), int(rng.integers(0, 12))
        rev = pd.DataFrame({"upLast30days": [up, up], "downLast30days": [dn, dn]}, index=["0q", "+1q"])
        info = {"sector": "Financial Services" if fin else ("Technology" if tech else "Industrials"),
                "forwardPE": float(rng.uniform(12, 32)), "trailingEps": eps_a[0], "forwardEps": eps_a[0] * 1.1,
                "sharesOutstanding": shares, "marketCap": px * shares,
                "enterpriseValue": px * shares + debt - cash}
        raw = RawFundamentals(ticker=t, info=info, income=income, q_income=q_income, balance=balance,
                              q_balance=q_balance, cashflow=cashflow, q_cashflow=q_cashflow,
                              eps_revisions=rev)
        if t == "UNH":  # exercise "missing statement keys" paths
            raw.cashflow = raw.cashflow.drop(index="Stock Based Compensation")
            raw.q_cashflow = raw.q_cashflow.drop(index="Stock Based Compensation")
            raw.eps_revisions = pd.DataFrame()
        if t == "LIN":
            raw.income = raw.income.drop(index=["EBIT", "EBITDA"])
            raw.q_income = raw.q_income.drop(index=["EBIT", "EBITDA"])
            raw.notes.append("Demo: EBIT/EBITDA lines deliberately removed")
        out[t] = raw
    return out
