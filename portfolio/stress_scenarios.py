"""
stress_scenarios.py — Forward-looking stress-scenario library & impact analysis
================================================================================
Production home for the M4 (Stress Test) feature.

Previously this logic lived in ``examples/run_m4.py``, which is excluded from
deployment (see ``.renderignore``) and is a CLI script — so the API could never
import it. It now lives inside the deployed ``portfolio`` package.

Two industry-standard ideas drive this module:

1. Empirically calibrated hypothetical shocks (forward-looking "what-if"),
   each defined as a market-factor move with a volatility regime multiplier
   and a correlation shift, calibrated to historical Indian-market episodes.

2. **Factor (beta) propagation.** A market shock does not hit every holding
   equally — a high-beta name falls more than a defensive one. Each asset's
   return shock is ``beta_i * market_shock``, so the portfolio P&L is
   ``beta_portfolio * market_shock``. This makes the stress test sensitive to
   the actual portfolio composition (the whole point of stress testing).
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from portfolio.portfolio_complete import MarketShock


def get_enhanced_scenarios() -> Dict[str, dict]:
    """
    Empirically calibrated forward-looking stress scenarios.

    Each entry carries the shock definition plus context (calibration basis,
    likelihood, duration, recovery) for reporting. ``return_shock`` is the
    *market-factor* move; it is propagated to each asset via beta downstream.
    """
    return {
        # ── SEVERE CRISIS ────────────────────────────────────────────────────
        "CRISIS_1": {
            "code": "CRISIS_1",
            "name": "Global Financial Crisis",
            "category": "🔴 SEVERE",
            "description": "Severe global credit crisis with liquidity freeze",
            "shock": MarketShock(name="Global Financial Crisis", return_shock=-0.45,
                                 volatility_shock=2.5, correlation_shock=0.40),
            "calibration": "2008: Nifty -52%, Vol 18%→45%, Corr 0.45→0.85",
            "likelihood": "Very Rare (1-2% annual)",
            "duration": "12-18 months", "recovery": "24-36 months",
            "impact": "40-50% portfolio decline",
        },
        "CRISIS_2": {
            "code": "CRISIS_2",
            "name": "Black Swan Pandemic/War",
            "category": "🔴 SEVERE",
            "description": "Unexpected catastrophic event",
            "shock": MarketShock(name="Black Swan Event", return_shock=-0.40,
                                 volatility_shock=2.8, correlation_shock=0.45),
            "calibration": "COVID Mar 2020: Nifty -38% in 1 month, Vol tripled",
            "likelihood": "Extremely Rare (<1% annual)",
            "duration": "1 month crash, 6 months total", "recovery": "6-12 months",
            "impact": "35-40% rapid drop",
        },
        # ── MODERATE ─────────────────────────────────────────────────────────
        "MOD_1": {
            "code": "MOD_1",
            "name": "India Economic Slowdown",
            "category": "🟠 MODERATE",
            "description": "GDP slowdown, policy uncertainty",
            "shock": MarketShock(name="India Economic Slowdown", return_shock=-0.22,
                                 volatility_shock=1.5, correlation_shock=0.18),
            "calibration": "2013 Taper Tantrum, 2018 NBFC crisis: -12% to -18%",
            "likelihood": "Moderate (10-15% annual)",
            "duration": "6-12 months", "recovery": "12-18 months",
            "impact": "15-25% decline",
        },
        "MOD_2": {
            "code": "MOD_2",
            "name": "US Fed Rate Shock",
            "category": "🟠 MODERATE",
            "description": "Fed tightening, FII outflows",
            "shock": MarketShock(name="Fed Rate Hikes", return_shock=-0.18,
                                 volatility_shock=1.4, correlation_shock=0.12),
            "calibration": "2022 Fed hikes: Nifty -15% to -20%",
            "likelihood": "Moderate (15-20% annual)",
            "duration": "3-9 months", "recovery": "6-12 months",
            "impact": "12-20% decline",
        },
        "MOD_3": {
            "code": "MOD_3",
            "name": "Banking/NBFC Crisis",
            "category": "🟠 MODERATE",
            "description": "Major bank failure, credit crunch",
            "shock": MarketShock(name="Banking Crisis", return_shock=-0.28,
                                 volatility_shock=1.7, correlation_shock=0.22),
            "calibration": "IL&FS 2018, Yes Bank 2020: -15% to -25%, BankNifty -40%",
            "likelihood": "Low-Moderate (5-8% annual)",
            "duration": "6-18 months", "recovery": "18-30 months",
            "impact": "20-30% decline",
        },
        # ── MILD ─────────────────────────────────────────────────────────────
        "MILD_1": {
            "code": "MILD_1",
            "name": "Healthy Market Correction",
            "category": "🟡 MILD",
            "description": "Normal profit booking",
            "shock": MarketShock(name="Market Correction", return_shock=-0.11,
                                 volatility_shock=1.25, correlation_shock=0.06),
            "calibration": "Typical 10-12% corrections (occur almost yearly)",
            "likelihood": "High (40-50% annual)",
            "duration": "1-3 months", "recovery": "3-6 months",
            "impact": "8-12% pullback",
        },
        "MILD_2": {
            "code": "MILD_2",
            "name": "Profit Booking/Rotation",
            "category": "🟡 MILD",
            "description": "Tactical selling, sector rotation",
            "shock": MarketShock(name="Profit Booking", return_shock=-0.07,
                                 volatility_shock=1.15, correlation_shock=0.03),
            "calibration": "Regular intra-month volatility: -5% to -8%",
            "likelihood": "Very High (60-70% annual)",
            "duration": "2-6 weeks", "recovery": "1-3 months",
            "impact": "5-8% dip",
        },
        # ── INDIA-SPECIFIC ───────────────────────────────────────────────────
        "INDIA_1": {
            "code": "INDIA_1",
            "name": "RBI Rate Hike Cycle",
            "category": "🔵 INDIA-SPECIFIC",
            "description": "RBI aggressive rate hikes",
            "shock": MarketShock(name="RBI Rate Hikes", return_shock=-0.15,
                                 volatility_shock=1.35, correlation_shock=0.10),
            "calibration": "2022-23: RBI +250bps in 9 months, Nifty -8% to -15%",
            "likelihood": "Moderate (15-20% annual)",
            "duration": "6-15 months", "recovery": "9-18 months",
            "impact": "10-15% decline",
        },
        "INDIA_2": {
            "code": "INDIA_2",
            "name": "Monsoon Failure",
            "category": "🔵 INDIA-SPECIFIC",
            "description": "Poor monsoon, rural demand hit",
            "shock": MarketShock(name="Monsoon Failure", return_shock=-0.09,
                                 volatility_shock=1.20, correlation_shock=0.05),
            "calibration": "2014-15 deficits: -5% to -10%, FMCG/Auto affected",
            "likelihood": "Moderate (10-15% annual)",
            "duration": "6-9 months", "recovery": "6-12 months",
            "impact": "6-10% decline",
        },
        "INDIA_3": {
            "code": "INDIA_3",
            "name": "Geopolitical Tension",
            "category": "🔵 INDIA-SPECIFIC",
            "description": "Border tensions (Pak/China)",
            "shock": MarketShock(name="Geopolitical Risk", return_shock=-0.10,
                                 volatility_shock=1.30, correlation_shock=0.08),
            "calibration": "Pulwama 2019, Galwan 2020: -3% to -8% (short-lived)",
            "likelihood": "Moderate (20-30% annual)",
            "duration": "2-12 weeks", "recovery": "1-3 months",
            "impact": "5-10% decline",
        },
        # ── SECTORAL ─────────────────────────────────────────────────────────
        "SECTOR_1": {
            "code": "SECTOR_1",
            "name": "IT Sector Crash",
            "category": "🔷 SECTORAL",
            "description": "Global tech selloff",
            "shock": MarketShock(name="Tech Crash", return_shock=-0.32,
                                 volatility_shock=1.9, correlation_shock=0.08),
            "calibration": "2022 selloff: Nifty IT -30% to -40%",
            "likelihood": "Moderate (10-15% annual)",
            "duration": "6-18 months", "recovery": "18-36 months",
            "impact": "Severe if IT-heavy (15-35%)",
        },
        "SECTOR_2": {
            "code": "SECTOR_2",
            "name": "Oil Price Shock",
            "category": "🔷 SECTORAL",
            "description": "Crude spike to $120+",
            "shock": MarketShock(name="Oil Shock", return_shock=-0.16,
                                 volatility_shock=1.4, correlation_shock=0.10),
            "calibration": "2008 oil at $147, 2022 at $130: -10% to -18%",
            "likelihood": "Moderate (15-20% annual)",
            "duration": "6-18 months", "recovery": "12-24 months",
            "impact": "12-18% decline",
        },
        # ── POSITIVE ─────────────────────────────────────────────────────────
        "POS_1": {
            "code": "POS_1",
            "name": "India Growth Boom",
            "category": "🟢 POSITIVE",
            "description": "Strong growth, reforms",
            "shock": MarketShock(name="Growth Boom", return_shock=0.25,
                                 volatility_shock=0.85, correlation_shock=-0.08),
            "calibration": "2014-17, 2020-21 rallies: +20% to +40%",
            "likelihood": "Moderate (15-20% annual)",
            "duration": "12-36 months", "recovery": "N/A (positive)",
            "impact": "20-35% gains",
        },
        "POS_2": {
            "code": "POS_2",
            "name": "Sector Bull Run",
            "category": "🟢 POSITIVE",
            "description": "Sectoral outperformance",
            "shock": MarketShock(name="Sector Rally", return_shock=0.18,
                                 volatility_shock=0.90, correlation_shock=-0.04),
            "calibration": "2020 Pharma, 2021 Metals, 2023 PSU: +30% to +100%",
            "likelihood": "Moderate-High (25-35% annual)",
            "duration": "12-30 months", "recovery": "N/A (positive)",
            "impact": "15-25% if well-positioned",
        },
    }


def compute_market_betas(
    asset_returns: pd.DataFrame,
    market_returns: pd.Series,
) -> pd.Series:
    """
    Single-factor (market) betas: beta_i = Cov(r_i, r_mkt) / Var(r_mkt).

    Used to propagate a market-factor shock to each asset. Returns a Series
    aligned to ``asset_returns.columns``; assets with no overlap default to 1.0
    (i.e. they move one-for-one with the market).
    """
    common = asset_returns.index.intersection(market_returns.index)
    betas = {}
    if len(common) >= 30:
        mkt = market_returns.loc[common]
        mkt_var = float(mkt.var())
        for col in asset_returns.columns:
            if mkt_var > 0:
                cov = float(asset_returns.loc[common, col].cov(mkt))
                betas[col] = cov / mkt_var
            else:
                betas[col] = 1.0
    else:
        betas = {col: 1.0 for col in asset_returns.columns}
    return pd.Series(betas)


def analyze_impact(
    weights: pd.Series,
    base_mu: pd.Series,
    base_sigma: pd.DataFrame,
    stressed_mu: pd.Series,
    stressed_sigma: pd.DataFrame,
    rf: float,
    pv: float,
) -> Dict[str, float]:
    """
    Compute the impact of a stressed (mu, sigma) versus the base parameters.

    The portfolio P&L of the scenario is the immediate revaluation implied by
    the change in (beta-propagated) returns: ``loss_pct = w·(stressed_mu - base_mu)``.
    Volatility and Sharpe are reported on both the base and stressed parameters.
    """
    w = weights.values
    base_ret = float(np.dot(w, base_mu.values))
    base_vol = float(np.sqrt(w @ base_sigma.values @ w))
    base_sharpe = (base_ret - rf) / base_vol if base_vol > 0 else 0.0

    stress_ret = float(np.dot(w, stressed_mu.values))
    stress_vol = float(np.sqrt(w @ stressed_sigma.values @ w))
    stress_sharpe = (stress_ret - rf) / stress_vol if stress_vol > 0 else 0.0

    ret_chg = stress_ret - base_ret
    vol_chg = (stress_vol / base_vol - 1) if base_vol > 0 else 0.0

    return {
        "base_return": base_ret,
        "stressed_return": stress_ret,
        "return_change": ret_chg,
        "base_vol": base_vol,
        "stressed_vol": stress_vol,
        "vol_change_pct": vol_chg,
        "base_sharpe": base_sharpe,
        "stressed_sharpe": stress_sharpe,
        "sharpe_change": stress_sharpe - base_sharpe,
        "portfolio_loss": ret_chg * pv,
        "loss_pct": ret_chg,
    }
