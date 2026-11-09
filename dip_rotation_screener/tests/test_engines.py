"""Engine tests run entirely on synthetic data - no network required."""
import numpy as np
import pandas as pd
import pytest

import config as C
import data_loader as dl
from demo_data import make_market_data, make_raw_fundamentals
from rotation_engine import (build_model_portfolio, classify_quadrant, detect_regime, pair_signals,
                             pair_spreads, relative_strength_table, rotation_havens, rrg_coordinates)
from screener_engine import (allocate_budget, build_ladder, compute_fundamentals, rsi, screen_universe,
                             technical_gauges)


@pytest.fixture(scope="module")
def md():
    return make_market_data(seed=7, rotation=True)


@pytest.fixture(scope="module")
def raw(md):
    return make_raw_fundamentals(md.prices)


# ---------------------------------------------------------------- loader
def test_backoff_retries_rate_limits_then_succeeds():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("429 Too Many Requests")
        return "ok"

    assert dl.with_backoff(flaky, sleep=sleeps.append) == "ok"
    assert len(calls) == 3 and len(sleeps) == 2
    assert 2 <= sleeps[0] <= 2.5 and 4 <= sleeps[1] <= 5      # exponential 2s, 4s (+ jitter)


def test_backoff_does_not_retry_programming_errors():
    with pytest.raises(ValueError):
        dl.with_backoff(lambda: (_ for _ in ()).throw(ValueError("bad")), sleep=lambda s: None)


def test_backoff_gives_up_after_retries():
    n = []
    with pytest.raises(RuntimeError):
        dl.with_backoff(lambda: n.append(1) or (_ for _ in ()).throw(RuntimeError("Too Many Requests")),
                        retries=2, sleep=lambda s: None)
    assert len(n) == 3


def test_get_row_aliases_and_missing_keys():
    df = pd.DataFrame({pd.Timestamp("2024-12-31"): [1.0, 2.0], pd.Timestamp("2023-12-31"): [3.0, np.nan]},
                      index=["Stock Based Compensation", "Other"])
    s = dl.get_row(df, ["Share Based Compensation", "stockbasedcompensation"])
    assert list(s.values) == [3.0, 1.0] and s.index.is_monotonic_increasing
    assert dl.get_row(df, ["Nope"]).empty and dl.get_row(pd.DataFrame(), ["x"]).empty


def test_load_market_data_all_fail_raises_clean_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("429 Too Many Requests")
    monkeypatch.setattr(dl, "_download_batch", boom)
    monkeypatch.setattr(dl, "_download_single", boom)
    with pytest.raises(dl.DataUnavailableError):
        dl.load_market_data(["SPY", "XLK"], sleep=lambda s: None)


def test_load_market_data_partial_batch_falls_back_per_ticker(monkeypatch):
    idx = pd.bdate_range("2023-01-02", periods=120)
    batch = pd.concat({"SPY": pd.DataFrame({"Close": np.linspace(1, 2, 120), "Volume": 1e6}, index=idx)}, axis=1)
    single = pd.DataFrame({"Close": np.linspace(5, 6, 120), "Volume": 1e6}, index=idx)
    monkeypatch.setattr(dl, "_download_batch", lambda *a, **k: batch)
    monkeypatch.setattr(dl, "_download_single", lambda sym, *a, **k: single if sym == "BRK-B" else (_ for _ in ()).throw(RuntimeError("nope")))
    out = dl.load_market_data(["SPY", "BRK.B", "ZZZZ"], sleep=lambda s: None)
    assert set(out.prices.columns) == {"SPY", "BRK.B"}          # BRK-B mapped back to display ticker
    assert out.failed == ["ZZZZ"] and any("ZZZZ" in w for w in out.warnings)


def test_fundamentals_circuit_breaker(monkeypatch):
    def limited(t, sleep=None):
        return dl.RawFundamentals(ticker=t, rate_limited=True, notes=["rate-limited"])
    monkeypatch.setattr(dl, "load_raw_fundamentals", limited)
    out, warns = dl.load_all_fundamentals(["A", "B", "C", "D"], pause=0, sleep=lambda s: None)
    assert "skipped" in out["C"].notes[0] and "skipped" in out["D"].notes[0]
    assert warns


# ---------------------------------------------------------------- rotation
def test_quadrants():
    assert classify_quadrant(101, 101) == "Leading"
    assert classify_quadrant(101, 99) == "Weakening"
    assert classify_quadrant(99, 99) == "Lagging"
    assert classify_quadrant(99, 101) == "Improving"
    assert classify_quadrant(np.nan, 100) == "n/a"


def test_rs_and_rrg_cover_all_11_sectors(md):
    etfs = list(C.GICS_SECTORS)
    rrg, tails = rrg_coordinates(md.prices, etfs)
    assert len(rrg) == 11 and set(rrg.Quadrant) <= {"Leading", "Weakening", "Lagging", "Improving"}
    assert all(t.index[-1] == md.prices.index[-1] for t in tails.values())
    rs = relative_strength_table(md.prices, etfs)
    assert {"RS_20d", "RS_60d", "RS_252d", "RS_ROC20", "RS_Accel"} <= set(rs.columns)
    manual = (md.prices["XLK"] / md.prices["SPY"]).iloc[-1] / (md.prices["XLK"] / md.prices["SPY"]).iloc[-21] - 1
    assert rs.loc["XLK", "RS_20d"] == pytest.approx(manual)


def test_pair_flags_and_regime_detects_synthetic_rotation(md):
    sig = pair_signals(pair_spreads(md.prices, C.PAIR_SPREADS))
    assert len(sig) == 4 and (sig.State != "Tech leading").sum() >= 2
    rrg, _ = rrg_coordinates(md.prices, list(C.GICS_SECTORS) + list(C.STYLE_ETFS))
    reg = detect_regime(sig, rrg, relative_strength_table(md.prices, list(rrg.index)))
    assert reg.severity >= 2 and "Rotation" in reg.headline and reg.inflows
    assert not set(reg.inflows) & set(C.GROWTH_ETFS)


def test_regime_intact_when_tech_leads():
    idx = pd.bdate_range("2023-01-02", periods=400)
    up = pd.Series(np.exp(np.linspace(0, 0.8, 400)), index=idx)
    flat = pd.Series(np.ones(400), index=idx)
    prices = pd.DataFrame({"XLK": up, "QQQ": up, "XLV": flat, "XLF": flat, "XLI": flat, "RSP": flat, "SPY": flat})
    sig = pair_signals(pair_spreads(prices, C.PAIR_SPREADS))
    assert (sig.State == "Tech leading").all()
    assert detect_regime(sig, pd.DataFrame(columns=["Quadrant"])).severity == 0


def test_model_portfolio_shifts_with_severity(md):
    rrg, _ = rrg_coordinates(md.prices, list(C.GICS_SECTORS) + list(C.STYLE_ETFS))
    px = md.prices.iloc[-1]
    lo = build_model_portfolio(0, rrg, px, 100_000)
    hi = build_model_portfolio(3, rrg, px, 100_000)
    assert lo.Target_Weight.sum() == pytest.approx(1) and hi.Target_Weight.sum() == pytest.approx(1)
    g = lambda d: d[d.Sleeve == "Growth"].Target_Weight.sum()
    assert g(lo) == pytest.approx(0.60) and g(hi) == pytest.approx(0.25)
    nd = build_model_portfolio(2, rrg, px, 100_000, include_defensive=False)
    assert nd.Target_Weight.sum() == pytest.approx(1) and "Defensive" not in set(nd.Sleeve)
    trades = build_model_portfolio(2, rrg, px, 100_000, current_values={"QQQ": 100_000})
    assert trades.loc["QQQ", "Action"] == "Trim" and (trades.Action == "Buy").any()


# ---------------------------------------------------------------- screener
def test_rsi_bounds():
    s = pd.Series(np.linspace(100, 50, 100))
    assert rsi(s).iloc[-1] < 5
    assert rsi(s[::-1].reset_index(drop=True)).iloc[-1] > 95


def test_technical_gauges_short_history_is_nan_not_error():
    g = technical_gauges(pd.Series(np.linspace(10, 12, 30)))
    assert np.isnan(g["SMA200"]) and not np.isnan(g["RSI14"])
    assert all(np.isnan(v) for v in technical_gauges(pd.Series(dtype=float)).values())


def test_compute_fundamentals_happy_path_and_missing_keys(md, raw):
    f = compute_fundamentals(raw["MSFT"], md.prices["MSFT"])
    assert f.roic_3y > 0 and f.fcf_adj < f.fcf_raw                       # SBC deducted
    assert not np.isnan(f.net_debt_ebitda) and not np.isnan(f.val_z)
    unh = compute_fundamentals(raw["UNH"], md.prices["UNH"])              # SBC + revisions removed
    assert unh.fcf_adj == pytest.approx(unh.fcf_raw) and np.isnan(unh.revision_breadth)
    assert any("SBC" in n for n in unh.notes)
    lin = compute_fundamentals(raw["LIN"], md.prices["LIN"])              # EBIT/EBITDA removed
    assert np.isnan(lin.roic_3y) and np.isnan(lin.net_debt_ebitda)
    empty = compute_fundamentals(dl.RawFundamentals(ticker="X"), md.prices["MSFT"])  # nothing at all
    assert np.isnan(empty.roic_3y) and empty.notes
    fin = compute_fundamentals(raw["JPM"], md.prices["JPM"])
    assert fin.is_financial and fin.roic_is_proxy and np.isnan(fin.net_debt_ebitda)


def test_screen_universe_scores_bounded_and_complete(md, raw):
    rrg, _ = rrg_coordinates(md.prices, list(C.GICS_SECTORS) + list(C.STYLE_ETFS))
    df = screen_universe(md.prices, md.volume, raw, rrg)
    assert len(df) == 14 and set(df.Universe) == {"Tech/AI", "Value"}
    for col in ("Dip Score", "Absorb Score"):
        assert df[col].dropna().between(0, 100).all() and df[col].notna().sum() >= 12
    assert df["Signal"].isin(["STRONG DIP BUY", "Watchlist", "No signal", "No data"]).all()


def test_screen_universe_survives_no_fundamentals(md):
    df = screen_universe(md.prices, md.volume, {}, None)
    assert len(df) == 14 and df["Dip Score"].notna().all()                 # technical component alone still scores
    assert (df["Dip Coverage"] < 0.5).all()                                # ...and says coverage is low
    assert (~df["Quality Pass"]).all()                                     # unknown quality never passes the gate


def test_ladder_structure_ordering_and_budget(md, raw):
    rrg, _ = rrg_coordinates(md.prices, list(C.GICS_SECTORS))
    row = screen_universe(md.prices, md.volume, raw, rrg).loc["NVDA"]
    lad = build_ladder(row, 30_000)
    assert list(lad.Weight) == [0.30, 0.40, 0.30]
    assert lad["Limit Price"].is_monotonic_decreasing and (lad["Limit Price"] < row.Price).all()
    assert lad["Cost $"].sum() <= 30_000 and lad.attrs["total_cost"] == pytest.approx(lad["Cost $"].sum())
    assert (lad["Budget $"].round(2) == [9000, 12000, 9000]).all()


def test_allocate_budget_caps_and_sums():
    a = allocate_budget(pd.Series({"A": 90, "B": 50, "C": 40}), 100_000, max_weight=0.5)
    assert a.sum() == pytest.approx(100_000) and a.max() <= 50_000 + 1e-6
    assert allocate_budget(pd.Series({"A": np.nan}), 1000).sum() == 0


def test_empty_responses_fail_fast():
    n, slept = [], []

    def empty():
        n.append(1)
        raise dl._EmptyResponse("empty")

    with pytest.raises(dl._EmptyResponse):
        dl.with_backoff(empty, retries=4, sleep=slept.append)
    assert len(n) == 2 and len(slept) == 1        # one retry only, not the full 2/4/8/16s ladder
