# Buy-the-Dip & Sector Rotation Screener

Streamlit + Pandas + Plotly + yfinance app with two jobs:

1. **Dip targets** - high-ROIC Tech/AI names that are oversold, cheap vs. their own history and financially sound.
2. **Rotation radar** - where capital is moving between Tech/Growth and Value/Cyclical/Defensive sectors
   (RRG quadrants, Tech-vs-Value pair spreads, regime banner) and which sectors are absorbing it.

> Educational analytics, not investment advice.

## Run

```bash
cd dip_rotation_screener
pip install -r requirements.txt
streamlit run app.py                 # live Yahoo Finance data
DIP_SCREENER_DEMO=1 streamlit run app.py   # start in synthetic demo mode (offline-safe)
pytest -q tests                      # engine + loader tests, no network needed
```

## Layout

| File | Responsibility |
|---|---|
| `config.py` | Universes, ticker→sector-ETF map, thresholds (`RotationParams`, `ScreenerParams`), sleeve weights |
| `data_loader.py` | Yahoo ingestion: batched prices with back-off, per-ticker fallback, fundamentals with circuit breaker, safe statement lookup |
| `rotation_engine.py` | RS table, RRG, pair spreads (50/200 SMA, ±2σ BB), regime detection, havens, model portfolio |
| `screener_engine.py` | Technical gauges, ROIC/solvency/FCF/valuation z-scores, composite scores, buy ladder, budget allocation |
| `demo_data.py` | Deterministic **synthetic** prices/statements (offline demo + tests) |
| `app.py` | Streamlit UI (3 tabs) |

## Method

**Rotation.** `RS = ETF / SPY`. Windows 20/60/252d report `RS_t / RS_{t-w} - 1`; `RS_Accel` = ROC20 now − ROC20 ten sessions ago.
RRG: `RS-Ratio = 100 · RS / SMA60(RS)`, `RS-Momentum = 100 + 10d ROC(%) of RS-Ratio`; quadrants split at 100/100
(Leading, Weakening, Lagging, Improving). Pairs XLK/XLV, XLK/XLF, XLK/XLI, QQQ/RSP are flagged **ACTIVE** when below their
50DMA *or* below the lower 20d/2σ Bollinger Band, **SEVERE** when both. Regime severity: 0 = none flagged, 1 = one pair,
2 = two+ pairs, 3 = three+ pairs with at least one SEVERE. Havens = non-growth ETFs ranked by quadrant then RS-momentum.

**Tech Dip Conviction (0-100)** - weights: technical capitulation 30%, valuation 25%, ROIC 20%, solvency 15%, positive
dilution-adjusted FCF 10%. Technical = RSI (30%), drawdown from 52w high (30%), distance to 200SMA (20%), volume spike on
down days vs. 20d average (20%). Valuation maxes out at z ≤ −1.5. Missing components are dropped and weights renormalised;
the `Dip Coverage` column shows how much of the score is backed by data. **STRONG DIP BUY** requires score ≥ 70, all quality
gates passed (ROIC ≥ 15% Tech / 10% Value, ND/EBITDA ≤ 2.5x, FCF − SBC > 0) **and** RSI < 35.

**Rotation Absorption (0-100)** - RS-momentum of the stock and its sector ETF (40%), 30-day EPS-revision breadth (30%),
low EV/EBITDA (30%, 25x → 0, 8x → 100).

**Ladder** - 30% pilot at spot −0.5%; 40% core at the nearest support (200SMA / lower BB / 52w low +5%) at least 4% below;
30% deep value at the price implying the multiple 2σ below its 3y median (floored at 70% of spot). Budget is split across
the top-N scores with a per-name cap.

**Model portfolio** - Growth (QQQ/XLK) / Value (RSP/XLF/XLI) / Defensive (XLV/XLP/XLU) sleeve weights step by regime severity
(60/30/10 → 25/50/25), with a bounded RS-momentum tilt inside each sleeve and optional rebalance trades vs. current holdings.

## Known data limitations (read these)

* **Valuation z-scores use a trailing basis.** Yahoo has no historical analyst estimates, so the 3y history is
  `price / as-of TTM EPS` and `EV / as-of TTM EBITDA` rebuilt from filed statements. *Forward* P/E and EV/NTM EBITDA are shown as
  current values; NTM EBITDA is a proxy (TTM EBITDA × forward/trailing EPS, clipped to 0.7-1.6x).
* Yahoo returns only ~4 fiscal years / ~5 quarters of statements, so "3-year" averages may use fewer points (noted per ticker).
* Financials (JPM, BRK.B): ROE replaces ROIC and leverage is treated as neutral - ND/EBITDA is not meaningful for them.
* "Flow proxy" is signed dollar volume, not creations/redemptions. EPS-revision breadth comes from `Ticker.eps_revisions`.
* `BRK.B` is mapped to Yahoo's `BRK-B` inside `data_loader.py` only.

## Resilience

* 429 / `YFRateLimitError` / timeouts retry at 2s, 4s, 8s, 16s (+jitter); empty responses retry once so a blocked network fails fast.
* Batch download failure → per-ticker fallback with a circuit breaker; partial results come back with warnings.
* Fundamentals: each statement is fetched independently; two consecutive throttled tickers open a breaker. Missing line items
  resolve via alias lists and degrade to `n/a` + a data-quality note, never an exception.
* Throttled or partial results are never cached (15 min prices / 6 h fundamentals otherwise). **Refresh data** clears the cache.
