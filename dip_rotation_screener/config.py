"""Static configuration: universes, ticker metadata and tunable thresholds.

Everything the engines treat as a "knob" lives here so the strategy can be
re-parameterised without touching the calculation code.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BENCHMARK = "SPY"

# ---------------------------------------------------------------------------
# ETF universes
# ---------------------------------------------------------------------------
# The 11 GICS sector SPDRs drive the RRG chart.
GICS_SECTORS: dict[str, str] = {
    "XLK": "Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLC": "Communication Services",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
}

# Thematic / style ETFs requested in the brief (not GICS sectors).
STYLE_ETFS: dict[str, str] = {
    "SMH": "Semiconductors",
    "QQQ": "Nasdaq 100",
    "RSP": "S&P 500 Equal Weight",
    "SCHD": "US Dividend Equity",
}

ETF_NAMES: dict[str, str] = {**GICS_SECTORS, **STYLE_ETFS, BENCHMARK: "S&P 500"}

# Style bucket of every ETF (used for flow attribution and portfolio sleeves).
ETF_STYLE: dict[str, str] = {
    # Tech / Growth
    "XLK": "Tech/Growth", "SMH": "Tech/Growth", "XLC": "Tech/Growth", "QQQ": "Tech/Growth",
    # Value / Financials / Cyclicals
    "XLF": "Value/Cyclical", "XLI": "Value/Cyclical", "XLE": "Value/Cyclical",
    "RSP": "Value/Cyclical", "SCHD": "Value/Cyclical", "XLY": "Value/Cyclical",
    "XLB": "Value/Cyclical",
    # Defensives
    "XLV": "Defensive", "XLU": "Defensive", "XLP": "Defensive", "XLRE": "Defensive",
}
GROWTH_ETFS = [t for t, s in ETF_STYLE.items() if s == "Tech/Growth"]

# (numerator, denominator) tech-vs-value pair spreads.
PAIR_SPREADS: list[tuple[str, str]] = [
    ("XLK", "XLV"),
    ("XLK", "XLF"),
    ("XLK", "XLI"),
    ("QQQ", "RSP"),
]

# ---------------------------------------------------------------------------
# Single-stock universes
# ---------------------------------------------------------------------------
TECH_UNIVERSE = ["MSFT", "NVDA", "GOOGL", "ASML", "TSM", "AAPL", "AMZN"]
VALUE_UNIVERSE = ["BRK.B", "JPM", "CAT", "GE", "UNH", "NEE", "LIN"]

# Display ticker -> Yahoo Finance symbol (only where they differ).
YAHOO_SYMBOLS: dict[str, str] = {"BRK.B": "BRK-B"}

# ticker -> (universe, sector label, mapped sector ETF used for RRG context)
STOCK_META: dict[str, tuple[str, str, str]] = {
    "MSFT": ("Tech/AI", "Software", "XLK"),
    "NVDA": ("Tech/AI", "Semiconductors", "SMH"),
    "GOOGL": ("Tech/AI", "Communication Services", "XLC"),
    "ASML": ("Tech/AI", "Semiconductor Equipment", "SMH"),
    "TSM": ("Tech/AI", "Semiconductors", "SMH"),
    "AAPL": ("Tech/AI", "Hardware", "XLK"),
    "AMZN": ("Tech/AI", "Consumer Discretionary / Cloud", "XLY"),
    "BRK.B": ("Value", "Financials", "XLF"),
    "JPM": ("Value", "Financials", "XLF"),
    "CAT": ("Value", "Industrials", "XLI"),
    "GE": ("Value", "Industrials", "XLI"),
    "UNH": ("Value", "Health Care", "XLV"),
    "NEE": ("Value", "Utilities", "XLU"),
    "LIN": ("Value", "Materials", "XLB"),
}

ALL_STOCKS = TECH_UNIVERSE + VALUE_UNIVERSE
ALL_ETFS = list(GICS_SECTORS) + list(STYLE_ETFS) + [BENCHMARK]
ALL_TICKERS = ALL_ETFS + ALL_STOCKS


def universe_of(ticker: str) -> str:
    return STOCK_META[ticker][0]


# ---------------------------------------------------------------------------
# Tunable parameters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RotationParams:
    rs_windows: tuple[int, ...] = (20, 60, 252)
    roc_window: int = 20            # ROC of the RS ratio (momentum acceleration baseline)
    rrg_norm_window: int = 60       # RS-Ratio = 100 * RS / SMA(RS, N)
    rrg_mom_window: int = 10        # RS-Momentum = 100 + 10d ROC(%) of RS-Ratio
    rrg_tail: int = 6               # weekly points drawn in the RRG tail
    pair_fast_ma: int = 50
    pair_slow_ma: int = 200
    bb_window: int = 20
    bb_sigma: float = 2.0
    flow_window: int = 20


@dataclass(frozen=True)
class ScreenerParams:
    rsi_window: int = 14
    rsi_oversold: float = 35.0
    sma_long: int = 200
    vol_window: int = 20
    nd_ebitda_max: float = 2.5
    roic_min: dict = field(default_factory=lambda: {"Tech/AI": 0.15, "Value": 0.10})
    val_lookback_days: int = 756      # ~3 trading years
    val_min_obs: int = 250
    val_extreme_z: float = -1.5
    tax_rate_default: float = 0.21
    # Composite weights (sum is renormalised over the components that have data).
    dip_weights: dict = field(default_factory=lambda: {
        "roic": 0.20, "solvency": 0.15, "fcf": 0.10, "valuation": 0.25, "technical": 0.30,
    })
    absorb_weights: dict = field(default_factory=lambda: {
        "rs_momentum": 0.40, "revisions": 0.30, "cheapness": 0.30,
    })
    # Signal thresholds
    strong_signal_score: float = 70.0
    watch_signal_score: float = 50.0
    # Ladder
    tranche_weights: tuple[float, float, float] = (0.30, 0.40, 0.30)


ROTATION = RotationParams()
SCREENER = ScreenerParams()

# Model-portfolio sleeve weights by rotation severity (growth, value, defensive).
SLEEVE_TARGETS: dict[int, tuple[float, float, float]] = {
    0: (0.60, 0.30, 0.10),
    1: (0.50, 0.35, 0.15),
    2: (0.35, 0.45, 0.20),
    3: (0.25, 0.50, 0.25),
}
SLEEVE_MEMBERS: dict[str, dict[str, float]] = {
    "Growth": {"QQQ": 0.60, "XLK": 0.40},
    "Value": {"RSP": 0.40, "XLF": 0.30, "XLI": 0.30},
    "Defensive": {"XLV": 0.40, "XLP": 0.30, "XLU": 0.30},
}
