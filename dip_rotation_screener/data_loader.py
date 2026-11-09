"""Yahoo Finance ingestion layer.

Design goals
------------
* Never crash the UI because Yahoo throttled us or omitted a field.
* Rate limits (HTTP 429 / ``YFRateLimitError`` / "Too Many Requests") are retried
  with exponential back-off + jitter, then degraded gracefully (per-ticker
  fallback, circuit breaker, partial results with human-readable warnings).
* This module is framework-agnostic; Streamlit caching is applied in ``app.py``.

All frames returned use *display* tickers (``BRK.B``) and tz-naive date indexes;
the Yahoo symbol mapping (``BRK-B``) only exists at the network boundary.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from config import YAHOO_SYMBOLS

try:  # yfinance is imported lazily so unit tests / demo mode work without it
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

log = logging.getLogger(__name__)

_TO_YAHOO = dict(YAHOO_SYMBOLS)
_FROM_YAHOO = {v: k for k, v in YAHOO_SYMBOLS.items()}

RATE_LIMIT_MARKERS = ("too many requests", "rate limit", "ratelimit", "429")
TRANSIENT_MARKERS = ("timed out", "timeout", "connection", "temporarily", "502", "503", "504")


class DataUnavailableError(RuntimeError):
    """Raised when no usable market data could be obtained at all."""


class _EmptyResponse(Exception):
    """Yahoo returned an empty frame (frequently a silent throttle)."""


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------
def is_rate_limit_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(m in text for m in RATE_LIMIT_MARKERS)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (_EmptyResponse, ConnectionError, TimeoutError)):
        return True
    if is_rate_limit_error(exc):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(m in text for m in TRANSIENT_MARKERS)


def with_backoff(
    fn: Callable[[], object],
    *,
    retries: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    label: str = "request",
    empty_retries: int = 1,
):
    """Run ``fn`` retrying rate-limit/transient failures with exponential back-off.

    Delays are 2s, 4s, 8s, 16s (+ up to 25% jitter). Non-retryable errors are
    raised immediately; after the last retry the final exception propagates.
    Empty responses (often a silent throttle *or* a hard network block) are retried at
    most ``empty_retries`` times so a blocked network fails fast instead of waiting 30s+.
    """
    attempt = 0
    empties = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised below
            if isinstance(exc, _EmptyResponse):
                empties += 1
                if empties > empty_retries:
                    raise
            if attempt >= retries or not _is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, delay * 0.25)
            log.warning("%s failed (%s: %s); retry %d/%d in %.1fs",
                        label, type(exc).__name__, exc, attempt + 1, retries, delay)
            sleep(delay)
            attempt += 1


# ---------------------------------------------------------------------------
# Market data (prices + volume)
# ---------------------------------------------------------------------------
@dataclass
class MarketData:
    prices: pd.DataFrame          # adjusted close, columns = display tickers
    volume: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    source: str = "yahoo"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _naive_index(obj):
    idx = pd.DatetimeIndex(obj.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    obj = obj.copy()
    obj.index = idx.normalize()
    return obj[~obj.index.duplicated(keep="last")].sort_index()


def _split_download(raw: pd.DataFrame, yahoo_symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalise the many shapes ``yf.download`` can return into close/volume frames."""
    close: dict[str, pd.Series] = {}
    vol: dict[str, pd.Series] = {}
    if raw is None or raw.empty:
        return pd.DataFrame(), pd.DataFrame()

    def grab(sub: pd.DataFrame, sym: str) -> None:
        col = "Close" if "Close" in sub.columns else ("Adj Close" if "Adj Close" in sub.columns else None)
        if col is None:
            return
        s = pd.to_numeric(sub[col], errors="coerce")
        if s.notna().sum() == 0:
            return
        close[_FROM_YAHOO.get(sym, sym)] = s
        if "Volume" in sub.columns:
            vol[_FROM_YAHOO.get(sym, sym)] = pd.to_numeric(sub["Volume"], errors="coerce")

    if isinstance(raw.columns, pd.MultiIndex):
        lvl0 = set(raw.columns.get_level_values(0))
        lvl1 = set(raw.columns.get_level_values(1))
        for sym in yahoo_symbols:
            if sym in lvl0:
                grab(raw[sym], sym)
            elif sym in lvl1:
                grab(raw.xs(sym, axis=1, level=1), sym)
    elif len(yahoo_symbols) == 1:
        grab(raw, yahoo_symbols[0])
    return pd.DataFrame(close), pd.DataFrame(vol)


def _download_batch(symbols: list[str], period: str, interval: str) -> pd.DataFrame:
    if yf is None:
        raise DataUnavailableError("yfinance is not installed (pip install yfinance).")
    raw = yf.download(symbols, period=period, interval=interval, auto_adjust=True,
                      group_by="ticker", progress=False, threads=False)
    if raw is None or raw.empty:
        raise _EmptyResponse("empty download")
    return raw


def _download_single(symbol: str, period: str, interval: str) -> pd.DataFrame:
    if yf is None:
        raise DataUnavailableError("yfinance is not installed (pip install yfinance).")
    raw = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if raw is None or raw.empty:
        raise _EmptyResponse(f"empty history for {symbol}")
    return raw


def load_market_data(
    tickers: Iterable[str],
    period: str = "4y",
    interval: str = "1d",
    min_rows: int = 60,
    sleep: Callable[[float], None] = time.sleep,
) -> MarketData:
    """Batch-download adjusted closes and volume with layered fallbacks.

    1. One batched request (with back-off on throttling).
    2. Any ticker missing from the batch is retried individually.
    3. Tickers with fewer than ``min_rows`` observations are dropped and reported.
    """
    tickers = list(dict.fromkeys(tickers))
    symbols = [_TO_YAHOO.get(t, t) for t in tickers]
    warnings: list[str] = []
    close, vol = pd.DataFrame(), pd.DataFrame()

    try:
        raw = with_backoff(lambda: _download_batch(symbols, period, interval),
                           sleep=sleep, label="batch download")
        close, vol = _split_download(raw, symbols)
    except DataUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        kind = "rate-limited by Yahoo Finance" if is_rate_limit_error(exc) else f"failed ({type(exc).__name__})"
        warnings.append(f"Batch price download {kind}; falling back to per-ticker requests.")

    missing = [t for t in tickers if t not in close.columns]
    fail_streak = 0
    for t in missing:
        # Circuit breaker: if Yahoo is blocking/throttling us, stop after 3 consecutive failures
        # instead of burning minutes retrying every ticker (partial results are still returned).
        if fail_streak >= (2 if close.empty else 3):
            warnings.append("Stopped per-ticker price fallback after repeated consecutive failures "
                            "(Yahoo rate limit or network block); try again in a few minutes.")
            break
        sym = _TO_YAHOO.get(t, t)
        try:
            raw = with_backoff(lambda s=sym: _download_single(s, period, interval),
                               retries=1, sleep=sleep, label=f"history {t}")
            c, v = _split_download(raw, [sym])
            if not c.empty:
                close[t] = c.iloc[:, 0]
                if not v.empty:
                    vol[t] = v.iloc[:, 0]
            fail_streak = 0
        except Exception as exc:  # noqa: BLE001
            fail_streak += 1
            log.info("No price data for %s: %s", t, exc)

    if close.empty:
        raise DataUnavailableError(
            "Yahoo Finance returned no price data (rate limit, network block or outage). "
            "Wait a few minutes and retry, or enable Demo data in the sidebar.")

    close = _naive_index(close)
    vol = _naive_index(vol.reindex(columns=close.columns)) if not vol.empty else pd.DataFrame(index=close.index)
    close = close.ffill(limit=3)

    failed = []
    for t in tickers:
        if t not in close.columns or close[t].notna().sum() < min_rows:
            failed.append(t)
            close = close.drop(columns=[t], errors="ignore")
            vol = vol.drop(columns=[t], errors="ignore")
    if failed:
        warnings.append("No/insufficient price history for: " + ", ".join(failed))

    return MarketData(prices=close, volume=vol.reindex(index=close.index, columns=close.columns),
                      warnings=warnings, failed=failed)


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------
@dataclass
class RawFundamentals:
    ticker: str
    info: dict = field(default_factory=dict)
    income: pd.DataFrame = field(default_factory=pd.DataFrame)
    q_income: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    q_balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    q_cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    eps_revisions: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)
    rate_limited: bool = False


def _fetch_attr(tk, attr: str, label: str, notes: list[str], sleep) -> object:
    """Read one lazily-evaluated yfinance attribute; failures become notes, not exceptions."""
    try:
        val = with_backoff(lambda: getattr(tk, attr), retries=3, sleep=sleep,
                           label=f"{tk.ticker}.{attr}")
    except Exception as exc:  # noqa: BLE001
        reason = "rate-limited" if is_rate_limit_error(exc) else type(exc).__name__
        notes.append(f"{label} unavailable ({reason})")
        if is_rate_limit_error(exc):
            raise
        return None
    return val


def load_raw_fundamentals(ticker: str, sleep: Callable[[float], None] = time.sleep) -> RawFundamentals:
    raw = RawFundamentals(ticker=ticker)
    if yf is None:
        raw.notes.append("yfinance not installed")
        return raw
    tk = yf.Ticker(_TO_YAHOO.get(ticker, ticker))
    plan = [
        ("info", "Company info", "info"),
        ("income_stmt", "Annual income statement", "income"),
        ("quarterly_income_stmt", "Quarterly income statement", "q_income"),
        ("balance_sheet", "Annual balance sheet", "balance"),
        ("quarterly_balance_sheet", "Quarterly balance sheet", "q_balance"),
        ("cashflow", "Annual cash flow", "cashflow"),
        ("quarterly_cashflow", "Quarterly cash flow", "q_cashflow"),
        ("eps_revisions", "EPS revisions", "eps_revisions"),
    ]
    for attr, label, dest in plan:
        try:
            val = _fetch_attr(tk, attr, label, raw.notes, sleep)
        except Exception:  # noqa: BLE001 - rate limit after retries: stop hammering this ticker
            raw.rate_limited = True
            break
        if val is None:
            continue
        if dest == "info":
            raw.info = dict(val) if isinstance(val, dict) else {}
        elif isinstance(val, pd.DataFrame) and not val.empty:
            if dest != "eps_revisions":
                val = val.copy()
                cols = pd.DatetimeIndex(pd.to_datetime(val.columns, errors="coerce"))
                val.columns = cols.tz_localize(None) if cols.tz is not None else cols
            setattr(raw, dest, val)
        else:
            raw.notes.append(f"{label} empty")
    return raw


def load_all_fundamentals(
    tickers: Iterable[str],
    pause: float = 0.35,
    max_consecutive_rate_limits: int = 2,
    progress: Callable[[int, int, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, RawFundamentals], list[str]]:
    """Fetch statements for many tickers sequentially with a circuit breaker.

    After ``max_consecutive_rate_limits`` throttled tickers in a row the remaining
    tickers are skipped (returned empty with a note) instead of hammering Yahoo.
    """
    tickers = list(tickers)
    out: dict[str, RawFundamentals] = {}
    warnings: list[str] = []
    streak = 0
    tripped = False
    for i, t in enumerate(tickers):
        if progress:
            progress(i, len(tickers), t)
        if tripped:
            out[t] = RawFundamentals(ticker=t, notes=["skipped: Yahoo rate limit circuit breaker open"])
            continue
        try:
            raw = load_raw_fundamentals(t, sleep=sleep)
        except Exception as exc:  # noqa: BLE001 - never let one ticker kill the batch
            raw = RawFundamentals(ticker=t, notes=[f"fundamentals failed: {type(exc).__name__}"])
        out[t] = raw
        streak = streak + 1 if raw.rate_limited else 0
        if streak >= max_consecutive_rate_limits:
            tripped = True
            warnings.append("Yahoo Finance rate-limited fundamentals requests; remaining tickers "
                            "were skipped. Technical/rotation data is unaffected - retry later.")
        sleep(pause)
    limited = [t for t, r in out.items() if r.rate_limited]
    if limited and not tripped:
        warnings.append("Rate-limited while fetching fundamentals for: " + ", ".join(limited))
    return out, warnings


# ---------------------------------------------------------------------------
# Safe statement access (shared with the screener engine)
# ---------------------------------------------------------------------------
def get_row(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    """Return the first matching statement line as a numeric Series sorted oldest->newest.

    Yahoo renames/omits line items between tickers and over time, so every lookup
    takes a list of aliases and degrades to an empty Series (never ``KeyError``).
    Matching is case/space-insensitive.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    norm = {str(i).replace(" ", "").lower(): i for i in df.index}
    for alias in aliases:
        key = alias.replace(" ", "").lower()
        if key in norm:
            s = pd.to_numeric(df.loc[norm[key]], errors="coerce")
            if isinstance(s, pd.DataFrame):  # duplicated index label
                s = s.iloc[0]
            s = s.dropna()
            s.index = pd.to_datetime(s.index, errors="coerce")
            return s[s.index.notna()].sort_index()
    return pd.Series(dtype=float)


def last_value(s: pd.Series) -> float:
    return float(s.iloc[-1]) if len(s) else float("nan")


def ttm_sum(quarterly: pd.Series, annual: pd.Series) -> float:
    """Trailing-twelve-month total: last 4 quarters, else latest fiscal year, else NaN."""
    if len(quarterly) >= 4:
        return float(quarterly.iloc[-4:].sum())
    return last_value(annual)


def clean_number(x, default: float = float("nan")) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if (np.isnan(v) or np.isinf(v)) else v
