"""Buy-the-Dip & Sector Rotation Screener - Streamlit UI.

Run:  streamlit run app.py
Educational analytics only - not investment advice.
"""
from __future__ import annotations

import os
import time
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config as C
from data_loader import DataUnavailableError, load_all_fundamentals, load_market_data
from demo_data import make_market_data, make_raw_fundamentals
from rotation_engine import (build_model_portfolio, detect_regime, money_flow_proxy, pair_signals,
                             pair_spreads, relative_strength_table, rotation_havens, rrg_coordinates)
from screener_engine import allocate_budget, bollinger, build_ladder, screen_universe

st.set_page_config(page_title="Dip & Rotation Screener", page_icon="📉", layout="wide")

QUAD_COLOR = {"Leading": "#2e9e6b", "Weakening": "#e0a526", "Lagging": "#d64545",
              "Improving": "#3b82d6", "n/a": "#888888"}
QUAD_FILL = {"Leading": "rgba(46,158,107,0.10)", "Weakening": "rgba(224,165,38,0.10)",
             "Lagging": "rgba(214,69,69,0.10)", "Improving": "rgba(59,130,214,0.10)"}
SEV_STYLE = {0: ("success", "🟢"), 1: ("warning", "🟡"), 2: ("error", "🟠"), 3: ("error", "🔴")}
MARKET_TTL, FUND_TTL = 15 * 60, 6 * 3600


# ---------------------------------------------------------------------------
# Data access (cached; failures/partial results are never cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def _store() -> dict:
    return {}


def cached_call(key, ttl: int, fn, ok=lambda r: True):
    store = _store()
    hit = store.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    res = fn()
    if ok(res):
        store[key] = (time.time(), res)
    return res


def load_everything(source: str, period: str):
    if source == "Demo (synthetic)":
        md = make_market_data()
        return md, make_raw_fundamentals(md.prices), []
    md = cached_call(("mkt", period), MARKET_TTL,
                     lambda: load_market_data(C.ALL_TICKERS, period=period),
                     ok=lambda m: not m.failed)
    stocks = [t for t in C.ALL_STOCKS if t in md.prices.columns]
    raw, fwarn = cached_call(("fund", tuple(stocks)), FUND_TTL,
                             lambda: load_all_fundamentals(stocks),
                             ok=lambda r: not r[1])
    return md, raw, fwarn


def fmt(x, spec: str) -> str:
    """Format a number, rendering NaN/inf as 'n/a' (missing data must never print 'nan')."""
    return "n/a" if x is None or not np.isfinite(x) else spec.format(x)


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------
def rrg_figure(rrg: pd.DataFrame, tails: dict[str, pd.DataFrame]) -> go.Figure:
    pad = 0.6
    xs = [rrg.RS_Ratio.min(), rrg.RS_Ratio.max()] + [v.RS_Ratio.min() for v in tails.values()] + [v.RS_Ratio.max() for v in tails.values()]
    ys = [rrg.RS_Momentum.min(), rrg.RS_Momentum.max()] + [v.RS_Momentum.min() for v in tails.values()] + [v.RS_Momentum.max() for v in tails.values()]
    hx = max(abs(min(xs) - 100), abs(max(xs) - 100)) + pad
    hy = max(abs(min(ys) - 100), abs(max(ys) - 100)) + pad
    fig = go.Figure()
    for name, (x0, x1, y0, y1) in {"Improving": (100 - hx, 100, 100, 100 + hy), "Leading": (100, 100 + hx, 100, 100 + hy),
                                   "Lagging": (100 - hx, 100, 100 - hy, 100), "Weakening": (100, 100 + hx, 100 - hy, 100)}.items():
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=QUAD_FILL[name], line_width=0, layer="below")
        fig.add_annotation(x=x0 + 0.02 * hx if x0 < 100 else x1 - 0.02 * hx, y=y1 - 0.04 * hy if y1 > 100 else y0 + 0.04 * hy,
                           text=f"<b>{name.upper()}</b>", showarrow=False, font=dict(color=QUAD_COLOR[name], size=12),
                           xanchor="left" if x0 < 100 else "right", yanchor="top" if y1 > 100 else "bottom")
    for t, h in tails.items():
        q = rrg.loc[t, "Quadrant"]
        fig.add_trace(go.Scatter(x=h.RS_Ratio, y=h.RS_Momentum, mode="lines", line=dict(color=QUAD_COLOR[q], width=1.2),
                                 opacity=0.45, hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=rrg.RS_Ratio, y=rrg.RS_Momentum, mode="markers+text", text=rrg.index, textposition="top center",
        marker=dict(size=13, color=[QUAD_COLOR[q] for q in rrg.Quadrant], line=dict(width=1, color="white")),
        customdata=np.c_[rrg.Name, rrg.Quadrant],
        hovertemplate="<b>%{text}</b> %{customdata[0]}<br>RS-Ratio %{x:.2f}<br>RS-Momentum %{y:.2f}"
                      "<br>%{customdata[1]}<extra></extra>", showlegend=False))
    fig.add_vline(x=100, line_width=1, line_color="gray")
    fig.add_hline(y=100, line_width=1, line_color="gray")
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(title="RS-Ratio (relative strength vs SPY, 100 = trend)", range=[100 - hx, 100 + hx], zeroline=False),
                      yaxis=dict(title="RS-Momentum (10d ROC of RS-Ratio, 100 = flat)", range=[100 - hy, 100 + hy], zeroline=False))
    return fig


def pair_figure(spreads: dict[str, pd.DataFrame], signals: pd.DataFrame, lookback: int) -> go.Figure:
    names = list(spreads)
    fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{n}  -  {signals.loc[n, 'State']}" if n in signals.index else n for n in names],
                        vertical_spacing=0.12, horizontal_spacing=0.07)
    for i, n in enumerate(names):
        r, c = divmod(i, 2)
        d = spreads[n].iloc[-lookback:]
        kw = dict(row=r + 1, col=c + 1)
        fig.add_trace(go.Scatter(x=d.index, y=d.BB_Up, line=dict(width=0), hoverinfo="skip", showlegend=False), **kw)
        fig.add_trace(go.Scatter(x=d.index, y=d.BB_Lo, line=dict(width=0), fill="tonexty", fillcolor="rgba(128,128,128,0.15)",
                                 hoverinfo="skip", name="Bollinger ±2σ (20d)", showlegend=i == 0), **kw)
        fig.add_trace(go.Scatter(x=d.index, y=d.Ratio, line=dict(color="#3b82d6", width=1.8), name="Ratio", showlegend=i == 0), **kw)
        fig.add_trace(go.Scatter(x=d.index, y=d.SMA50, line=dict(color="#e0a526", width=1.3), name="50d SMA", showlegend=i == 0), **kw)
        fig.add_trace(go.Scatter(x=d.index, y=d.SMA200, line=dict(color="#888888", width=1.3, dash="dash"), name="200d SMA", showlegend=i == 0), **kw)
        brk = d[d.Ratio < d.BB_Lo]
        if len(brk):
            fig.add_trace(go.Scatter(x=brk.index, y=brk.Ratio, mode="markers", marker=dict(color="#d64545", size=6),
                                     name="Break -2σ", showlegend=i == 0), **kw)
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.06))
    return fig


def price_figure(close: pd.Series, volume: pd.Series | None, ladder: pd.DataFrame | None, lookback: int = 504) -> go.Figure:
    sma200 = close.rolling(200).mean()
    sma50 = close.rolling(50).mean()
    bb = bollinger(close)
    d = close.index[-lookback:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=d, y=bb.Upper.loc[d], line=dict(width=0), hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=d, y=bb.Lower.loc[d], line=dict(width=0), fill="tonexty", fillcolor="rgba(128,128,128,0.18)",
                             name="Bollinger ±2σ (20d)", hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d, y=close.loc[d], line=dict(color="#3b82d6", width=2), name="Close"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d, y=sma50.loc[d], line=dict(color="#e0a526", width=1.2), name="50d SMA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d, y=sma200.loc[d], line=dict(color="#d64545", width=1.6), name="200d SMA"), row=1, col=1)
    if ladder is not None:
        for _, r in ladder.iterrows():
            fig.add_hline(y=r["Limit Price"], line_dash="dot", line_color="#2e9e6b", row=1, col=1,
                          annotation_text=f"{r['Tranche'].split(' - ')[0]}: ${r['Limit Price']:,.2f}", annotation_position="bottom right")
    if volume is not None and volume.notna().any():
        fig.add_trace(go.Bar(x=d, y=volume.reindex(d), marker_color="rgba(128,128,128,0.5)", name="Volume", showlegend=False), row=2, col=1)
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.04), hovermode="x unified")
    return fig


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.title("Buy-the-Dip & Sector Rotation Screener")
st.caption("Find high-quality tech names sold off in sector drawdowns, and see where capital is rotating. "
           "Educational analytics, not investment advice.")

with st.sidebar:
    st.header("Data")
    source = st.radio("Source", ["Yahoo Finance (live)", "Demo (synthetic)"], key="source",
                      index=1 if os.environ.get("DIP_SCREENER_DEMO") else 0, help="Demo uses generated, non-real data so the app "
                      "works offline or when Yahoo rate-limits you.")
    period = st.selectbox("Price history", ["3y", "4y", "5y"], index=1,
                          help="3-year valuation z-scores need ~3y of prices plus the 200d SMA warm-up.")
    if st.button("Refresh data", width="stretch"):
        _store().clear()
        st.rerun()

    st.header("Execution")
    budget = st.number_input("Total dip-buying budget ($)", 1_000, 10_000_000, 50_000, 1_000)
    top_n = st.slider("Spread budget across top N targets", 1, 10, 3)
    max_w = st.slider("Max weight per name", 0.10, 1.0, 0.35, 0.05)

    with st.expander("Screening thresholds"):
        rsi_os = st.slider("RSI oversold below", 20, 50, 35)
        nd_max = st.slider("Max Net Debt / EBITDA (x)", 0.5, 6.0, 2.5, 0.1)
        roic_t = st.slider("Min 3y ROIC - Tech/AI (%)", 5, 30, 15)
        roic_v = st.slider("Min 3y ROIC - Value (%)", 5, 30, 10)
    params = replace(C.SCREENER, rsi_oversold=float(rsi_os), nd_ebitda_max=float(nd_max),
                     roic_min={"Tech/AI": roic_t / 100, "Value": roic_v / 100})

# ---------------------------------------------------------------------------
# Load + compute
# ---------------------------------------------------------------------------
try:
    with st.spinner("Loading market data and fundamentals (first load can take a minute)..."):
        md, raw, fund_warnings = load_everything(source, period)
except DataUnavailableError as exc:
    st.error(f"**Could not load market data.** {exc}")
    st.info("Pick **Demo (synthetic)** in the sidebar to explore the app with generated data.")
    st.stop()
except Exception as exc:  # noqa: BLE001 - last-resort guard so the UI never shows a raw traceback
    st.error(f"Unexpected error while loading data: {type(exc).__name__}: {exc}")
    st.stop()

prices, volume = md.prices, md.volume
if source == "Demo (synthetic)":
    st.warning("**DEMO MODE** - all prices and fundamentals are synthetic. Do not trade on them.")
for w in [*md.warnings, *fund_warnings]:
    if not w.startswith("DEMO"):
        st.warning(w)

if C.BENCHMARK not in prices.columns:
    st.error("SPY benchmark data is missing, so relative-strength analytics cannot run. Hit **Refresh data** and retry.")
    st.stop()

sector_etfs = [t for t in C.GICS_SECTORS if t in prices.columns]
style_etfs = [t for t in C.STYLE_ETFS if t in prices.columns]
rs_table = relative_strength_table(prices, sector_etfs + style_etfs)
rrg_all, tails_all = rrg_coordinates(prices, sector_etfs + style_etfs)
spreads = pair_spreads(prices, C.PAIR_SPREADS)
signals = pair_signals(spreads)
regime = detect_regime(signals, rrg_all, rs_table)
flow = money_flow_proxy(prices, volume, sector_etfs + style_etfs)
screen = screen_universe(prices, volume, raw, rrg_all, params=params)

tab1, tab2, tab3 = st.tabs(["🧭 Sector Rotation Radar", "📉 Dip Screener & Execution", "⚖️ ETF Asset Allocation Tracker"])

# ===========================================================================
# TAB 1 - Sector Rotation Radar
# ===========================================================================
with tab1:
    kind, icon = SEV_STYLE[regime.severity]
    getattr(st, kind)(f"### {icon} {regime.headline}\n**{regime.label}** - {regime.detail}")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Relative Rotation Graph vs SPY")
        incl = st.checkbox("Include SMH / QQQ / RSP / SCHD", value=False)
        keep = sector_etfs + (style_etfs if incl else [])
        r = rrg_all.loc[[t for t in keep if t in rrg_all.index]]
        if r.empty:
            st.info("Not enough history to compute RRG coordinates.")
        else:
            st.plotly_chart(rrg_figure(r, {t: tails_all[t] for t in r.index}), width="stretch")
            st.caption("Tails show the last 6 weeks. Clockwise drift Improving → Leading → Weakening → Lagging is the normal cycle.")
    with right:
        st.subheader("Rotation havens (absorbing liquidity)")
        hv = rotation_havens(rrg_all, rs_table, top_n=5)
        if not hv.empty:
            hv = hv.join(flow, how="left")
            st.dataframe(hv[["Quadrant", "RS_Ratio", "RS_Momentum", "Flow20"]].rename(columns={"Flow20": "Flow proxy"}),
                         width="stretch",
                         column_config={"RS_Ratio": st.column_config.NumberColumn("RS-Ratio", format="%.2f"),
                                        "RS_Momentum": st.column_config.NumberColumn("RS-Mom", format="%.2f"),
                                        "Flow proxy": st.column_config.NumberColumn(format="%.2f",
                                            help="20d signed dollar-volume flow in [-1, 1]. A proxy - real fund flows are not available from Yahoo.")})
        st.subheader("Tech-vs-Value pair spreads")
        if not signals.empty:
            st.dataframe(signals[["vs_SMA50_%", "BB_Z", "State"]], width="stretch",
                         column_config={"vs_SMA50_%": st.column_config.NumberColumn("vs 50d %", format="%.2f"),
                                        "BB_Z": st.column_config.NumberColumn("BB z", format="%.2f")})

    st.subheader("Pair spread time-series")
    lb = st.radio("Window", ["6M", "1Y", "2Y"], index=1, horizontal=True)
    if spreads:
        st.plotly_chart(pair_figure(spreads, signals, {"6M": 126, "1Y": 252, "2Y": 504}[lb]), width="stretch")

    st.subheader("Relative strength vs SPY")
    if not rs_table.empty:
        show = rs_table.copy()
        for c in ("RS_20d", "RS_60d", "RS_252d", "RS_ROC20", "RS_Accel"):
            show[c] = show[c] * 100
        st.dataframe(show.drop(columns=["RS"]).join(rrg_all[["Quadrant"]]).sort_values("RS_60d", ascending=False),
                     width="stretch",
                     column_config={c: st.column_config.NumberColumn(c.replace("_", " "), format="%.2f%%")
                                    for c in ("RS_20d", "RS_60d", "RS_252d", "RS_ROC20", "RS_Accel")})
        st.caption("RS windows = (ETF/SPY ratio today ÷ ratio N days ago) − 1. Accel = ROC20 now − ROC20 ten sessions ago.")

# ===========================================================================
# TAB 2 - Dip Screener & Execution
# ===========================================================================
def render_dip_tab() -> None:
    if screen.empty:
        st.info("No single-stock data available.")
        return

    f1, f2, f3, f4 = st.columns(4)
    uni = f1.multiselect("Universe", ["Tech/AI", "Value"], default=["Tech/AI", "Value"])
    sigs = f2.multiselect("Signal", ["STRONG DIP BUY", "Watchlist", "No signal", "No data"],
                          default=["STRONG DIP BUY", "Watchlist", "No signal", "No data"])
    rsi_max = f3.slider("RSI at most", 10, 100, 100)
    qonly = f4.checkbox("Quality gates passed only", value=False)
    view = screen[screen.Universe.isin(uni) & screen.Signal.isin(sigs) & (screen.RSI.fillna(0) <= rsi_max)]
    if qonly:
        view = view[view["Quality Pass"]]
    view = view.sort_values("Dip Score", ascending=False, na_position="last")

    cols = ["Sector", "RSI", "Drawdown %", "ROIC % (3y)", "Valuation Z", "Dip Score", "Absorb Score", "Signal"]
    event = st.dataframe(
        view[cols], width="stretch", hide_index=False, on_select="rerun", selection_mode="single-row", key="grid",
        column_config={
            "RSI": st.column_config.NumberColumn(format="%.1f"),
            "Drawdown %": st.column_config.NumberColumn(format="%.1f"),
            "Dist SMA200 %": st.column_config.NumberColumn(format="%.1f"),
            "ROIC % (3y)": st.column_config.NumberColumn(format="%.1f"),
            "ND/EBITDA": st.column_config.NumberColumn(format="%.2f"),
            "Valuation Z": st.column_config.NumberColumn(format="%.2f", help="Mean z of P/E and EV/EBITDA vs 3y median (trailing basis). ≤ -1.5 = extreme discount."),
            "Dip Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f",
                                                         help="Tech Dip Conviction (0-100)"),
            "Absorb Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f",
                                                            help="Rotation Absorption (0-100)"),
        })
    if view.empty:
        st.info("No tickers match the current filters.")
        return

    picked = event.selection.rows
    if picked and st.session_state.get("_last_grid") != view.index[picked[0]]:
        st.session_state["_last_grid"] = st.session_state["drill"] = view.index[picked[0]]
    if st.session_state.get("drill") not in view.index:
        st.session_state["drill"] = view.index[0]
    tkr = st.selectbox("Drill-down ticker (or click a table row)", list(view.index), key="drill")
    row = screen.loc[tkr]

    # --- header metrics -------------------------------------------------------
    st.markdown(f"### {tkr} - {row.Sector}  ·  {row.Signal}")
    m = st.columns(6)
    m[0].metric("Price", f"${row.Price:,.2f}")
    m[1].metric("Dip Score", fmt(row["Dip Score"], "{:.0f}/100"),
                help=f"Data coverage of score: {row['Dip Coverage']:.0%}")
    m[2].metric("RSI(14)", fmt(row.RSI, "{:.1f}"))
    m[3].metric("Drawdown", fmt(row["Drawdown %"], "{:.1f}%"))
    m[4].metric("ROIC 3y", fmt(row["ROIC % (3y)"], "{:.1f}%"))
    m[5].metric("Valuation Z", fmt(row["Valuation Z"], "{:+.2f}"))

    # --- ladder ---------------------------------------------------------------
    pool = view[view["Dip Score"].notna()].head(top_n)
    alloc = allocate_budget(pool["Dip Score"], budget, max_w)
    default_pos = float(alloc.get(tkr, budget * min(max_w, 1 / top_n)))
    pos_budget = st.number_input(f"Position budget for {tkr} ($)", 0.0, float(budget) * 10, round(default_pos, 2), 500.0,
                                 help="Defaults to the score-weighted, capped share of your total budget if this ticker is in the top N.",
                                 key=f"pos_{tkr}_{budget}_{top_n}_{max_w}")
    ladder = build_ladder(row, pos_budget, params.tranche_weights) if pos_budget > 0 else None

    st.plotly_chart(price_figure(prices[tkr].dropna(), volume[tkr] if tkr in volume else None, ladder), width="stretch")

    st.markdown("**3-stage tranche limit orders**")
    if ladder is not None:
        st.dataframe(ladder, width="stretch", hide_index=True, column_config={
            "Weight": st.column_config.NumberColumn(format="percent"),
            "Limit Price": st.column_config.NumberColumn(format="$%.2f"),
            "vs Spot %": st.column_config.NumberColumn(format="%.1f%%"),
            "Budget $": st.column_config.NumberColumn(format="dollar"),
            "Cost $": st.column_config.NumberColumn(format="dollar"),
            "Basis": st.column_config.TextColumn(width="large")})
        a = st.columns(3)
        a[0].metric("If all fill: avg cost", f"${ladder.attrs['avg_cost']:,.2f}" if ladder.attrs["total_shares"] else "n/a")
        a[1].metric("Capital deployed", f"${ladder.attrs['total_cost']:,.0f}")
        a[2].metric("Shares", f"{ladder.attrs['total_shares']:,}")
        if not row["Quality Pass"] or row.Signal != "STRONG DIP BUY":
            st.caption("⚠️ Not a STRONG DIP BUY: quality gates failed/unknown, or conviction/RSI thresholds are unmet. "
                       "Treat the ladder as a what-if.")
    else:
        st.info("Set a position budget above zero to generate the ladder.")

    # --- details + peers --------------------------------------------------------
    d1, d2 = st.columns(2, gap="large")
    with d1:
        st.markdown("**Fundamentals snapshot**")
        snap = pd.DataFrame({
            "Metric": ["3y avg ROIC", "Net debt / EBITDA", "Dilution-adj FCF", "Forward P/E", "EV / NTM EBITDA (proxy)",
                       "EPS revision breadth (30d)", "Rotation Absorption score"],
            "Value": [fmt(row["ROIC % (3y)"], "{:.1f}%"), fmt(row["ND/EBITDA"], "{:.2f}x"),
                      fmt(row["FCF adj ($B)"], "${:.2f}B"), fmt(row["Fwd P/E"], "{:.1f}"),
                      fmt(row["EV/NTM EBITDA"], "{:.1f}x"), fmt(row["Rev Breadth"], "{:+.2f}"),
                      fmt(row["Absorb Score"], "{:.0f}/100")]})
        st.dataframe(snap, hide_index=True, width="stretch")
        if row.Notes:
            with st.expander("Data-quality notes (missing/estimated inputs)"):
                st.write(row.Notes)
    with d2:
        st.markdown("**Peer comparison**")
        peers = screen[screen.Universe == row.Universe]
        fig = go.Figure(go.Bar(x=peers.index, y=peers["Dip Score"],
                               marker_color=["#3b82d6" if t == tkr else "rgba(128,128,128,0.55)" for t in peers.index]))
        fig.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Dip Score")
        st.plotly_chart(fig, width="stretch")
        rebased = prices[list(peers.index)].iloc[-252:]
        rebased = rebased / rebased.iloc[0] * 100
        fig2 = go.Figure()
        for t in rebased.columns:
            fig2.add_trace(go.Scatter(x=rebased.index, y=rebased[t], name=t, line=dict(width=2.5 if t == tkr else 1,
                                                                                    color="#3b82d6" if t == tkr else None)))
        fig2.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="1y rebased = 100")
        st.plotly_chart(fig2, width="stretch")
    num = lambda f="%.1f": st.column_config.NumberColumn(format=f)  # noqa: E731
    st.dataframe(peers[["Sector", "RSI", "Drawdown %", "ROIC % (3y)", "ND/EBITDA", "Valuation Z", "Dip Score", "Absorb Score", "Signal"]],
                 width="stretch", column_config={"RSI": num(), "Drawdown %": num(), "ROIC % (3y)": num(), "ND/EBITDA": num("%.2f"),
                                                 "Valuation Z": num("%.2f"), "Dip Score": num("%.0f"), "Absorb Score": num("%.0f")})

with tab2:
    render_dip_tab()

# ===========================================================================
# TAB 3 - ETF Asset Allocation Tracker
# ===========================================================================
with tab3:
    st.subheader("Rotation-aware model portfolio")
    g1, g2, g3, g4 = st.columns(4)
    mode = g1.selectbox("Regime", ["Auto (detected)", "0 - Tech leadership", "1 - Early warning", "2 - Active rotation", "3 - Severe rotation"])
    sev = regime.severity if mode.startswith("Auto") else int(mode[0])
    port_budget = g2.number_input("Portfolio value ($)", 1_000, 100_000_000, 100_000, 5_000)
    tilt = g3.slider("Momentum tilt inside sleeves", 0.0, 0.6, 0.25, 0.05,
                     help="0 = fixed base weights. Higher = lean harder into ETFs with stronger RS-momentum.")
    incl_def = g4.checkbox("Include defensive ballast (XLV/XLP/XLU)", value=True)
    st.caption(f"Detected regime: **{regime.label}** (severity {regime.severity}). Using severity **{sev}**.")

    last_px = prices.iloc[-1]
    base = build_model_portfolio(sev, rrg_all, last_px, port_budget, incl_def, tilt)

    cur: dict[str, float] = {}
    with st.expander("Optional: enter current holdings ($) to get rebalance trades"):
        seed = pd.DataFrame({"Ticker": base.index, "Current_$": 0.0})
        edited = st.data_editor(seed, hide_index=True, width="stretch", disabled=["Ticker"],
                                column_config={"Current_$": st.column_config.NumberColumn(min_value=0.0, step=500.0, format="dollar")})
        cur = dict(zip(edited.Ticker, edited["Current_$"]))
    pf = build_model_portfolio(sev, rrg_all, last_px, port_budget, incl_def, tilt, cur if sum(cur.values()) > 0 else None)

    p1, p2 = st.columns([2, 3], gap="large")
    with p1:
        sleeve_color = {"Growth": "#3b82d6", "Value": "#2e9e6b", "Defensive": "#e0a526"}
        sleeves = pf.groupby("Sleeve")["Target_Weight"].sum().reindex(list(sleeve_color)).dropna()
        fig = go.Figure(go.Pie(labels=sleeves.index, values=sleeves.values, hole=0.55, sort=False,
                               marker=dict(colors=[sleeve_color[x] for x in sleeves.index]),
                               texttemplate="%{label}<br>%{percent}"))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with p2:
        show = pf.copy()
        show["Target_Weight"] = show["Target_Weight"] * 100
        cc = {"Target_Weight": st.column_config.NumberColumn("Weight %", format="%.1f%%"),
              "Target_$": st.column_config.NumberColumn("Target $", format="dollar"),
              "Price": st.column_config.NumberColumn(format="$%.2f"),
              "Current_$": st.column_config.NumberColumn("Current $", format="dollar"),
              "Trade_$": st.column_config.NumberColumn("Trade $", format="dollar"),
              "Target_Shares": st.column_config.NumberColumn("Shares", format="%d")}
        st.dataframe(show, width="stretch", column_config=cc)

    st.markdown("**Sleeve weights by regime** (rows = severity; the active row is your current setting)")
    mat = pd.DataFrame(C.SLEEVE_TARGETS, index=["Growth", "Value", "Defensive"]).T * 100
    mat.index = ["0 - Tech leadership", "1 - Early warning", "2 - Active rotation", "3 - Severe rotation"]
    st.dataframe(mat.style.format("{:.0f}%").apply(lambda r: ["font-weight:bold" if r.name == mat.index[sev] else "" for _ in r], axis=1),
                 width="stretch")
    st.caption("Rule of thumb: severity is driven by how many of XLK/XLV, XLK/XLF, XLK/XLI and QQQ/RSP sit below their 50DMA or "
               "-2σ Bollinger band. Within each sleeve, weights tilt toward ETFs with stronger RS-momentum vs SPY. "
               "Model weights are illustrative, not personalised advice.")
