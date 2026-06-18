"""
Shared price-panel validation for portfolio APIs.

Avoids dropping entire rows when one ticker has sparse history; filters bad
columns first, then aligns on overlapping trading days with a minimum bar count.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_MAX_NAN_FRAC = 0.30
DEFAULT_MIN_OVERLAP_ROWS = 60
DEFAULT_MIN_TICKERS = 2


def prepare_price_panel(
    prices: pd.DataFrame,
    requested_tickers: list[str] | None = None,
    *,
    max_nan_fraction: float = DEFAULT_MAX_NAN_FRAC,
    min_overlap_rows: int = DEFAULT_MIN_OVERLAP_ROWS,
    min_tickers: int = DEFAULT_MIN_TICKERS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Validate and align a close-price DataFrame for optimisation pipelines.

    Returns
    -------
    (prices_aligned, diagnostics)
        prices_aligned has only columns that passed validation and rows where
        all retained tickers have data (pairwise-complete calendar).
    """
    diag: dict[str, Any] = {
        "requested_tickers": list(requested_tickers or []),
        "input_columns": list(prices.columns) if prices is not None else [],
        "dropped_high_nan": [],
        "dropped_empty": [],
        "dropped_low_overlap": [],
        "valid_tickers": [],
        "rows_before": int(len(prices)) if prices is not None else 0,
        "rows_after": 0,
    }

    if prices is None or prices.empty:
        raise ValueError(
            "No price data was returned from the market data provider. "
            "Check ticker symbols (use NSE suffix e.g. RELIANCE.NS) and try again."
        )

    panel = prices.copy()
    if isinstance(panel.columns, pd.MultiIndex):
        panel.columns = panel.columns.get_level_values(0)

    if requested_tickers:
        present = [t for t in requested_tickers if t in panel.columns]
        missing = [t for t in requested_tickers if t not in panel.columns]
        if missing:
            logger.warning("Tickers missing from download: %s", missing)
            diag["missing_from_download"] = missing
        if not present:
            raise ValueError(
                f"None of the requested tickers produced data: {requested_tickers}. "
                "Verify symbols or network access to Yahoo Finance."
            )
        panel = panel[present]

    for col in list(panel.columns):
        series = panel[col]
        if series.notna().sum() == 0:
            diag["dropped_empty"].append(col)
            panel = panel.drop(columns=[col])
            continue
        nan_frac = float(series.isna().mean())
        if nan_frac >= max_nan_fraction:
            diag["dropped_high_nan"].append({"ticker": col, "nan_fraction": round(nan_frac, 4)})
            panel = panel.drop(columns=[col])

    if panel.shape[1] < min_tickers:
        raise ValueError(
            f"Only {panel.shape[1]} ticker(s) with sufficient price history "
            f"(need at least {min_tickers}). "
            f"Removed for missing data: {diag['dropped_high_nan'] + diag['dropped_empty']}. "
            "Try fewer tickers or symbols with longer listing history."
        )

    panel = panel.ffill(limit=5).dropna(how="all")
    aligned = panel.dropna(how="any")
    diag["rows_after_pairwise"] = int(len(aligned))

    if len(aligned) < min_overlap_rows:
        per_ticker = {}
        for col in panel.columns:
            valid_idx = panel[col].dropna().index
            per_ticker[col] = int(len(valid_idx))
        raise ValueError(
            f"Insufficient overlapping trading days ({len(aligned)} rows, "
            f"need at least {min_overlap_rows}). "
            f"Per-ticker history length: {per_ticker}. "
            "Remove recently listed or illiquid names, or use a shorter portfolio list."
        )

    diag["valid_tickers"] = list(aligned.columns)
    diag["rows_after"] = int(len(aligned))
    logger.info(
        "Price panel ready: %d tickers, %d rows (dropped high-NaN: %s)",
        len(aligned.columns),
        len(aligned),
        [d["ticker"] if isinstance(d, dict) else d for d in diag["dropped_high_nan"]],
    )
    return aligned, diag
