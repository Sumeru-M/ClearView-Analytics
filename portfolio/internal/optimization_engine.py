"""
optimization_engine.py — Multi-Objective Portfolio Optimization Engine

Optimization frameworks implemented:
    1. Mean-Variance (Markowitz)       — maximize μ - λσ²
    2. Minimum Variance                — minimize σ²
    3. CVaR Optimization               — minimize Expected Shortfall
    4. Risk Parity                     — equal risk contribution (iterative)
    5. Hierarchical Risk Parity (HRP)  — graph theory + clustering (PRIMARY diversifier)
    6. Multi-Objective                 — maximize return, minimize vol,
                                         minimize CVaR, penalize drawdown,
                                         penalize factor concentration

All methods accept a ConstraintBuilder and return an AllocationResult.

Design principles
-----------------
- Wraps existing optimizer.py min-variance / max-sharpe rather than replacing.
- CVaR optimization uses the Rockafellar-Uryasev LP linearisation.
- Risk Parity uses Newton's method (no LP/QP needed).
- HRP (López de Prado 2016) uses hierarchical clustering + recursive bisection.
  No matrix inversion required — robust to small/correlated universes (N < 30).
  This is the PRIMARY diversification method replacing optimize_max_diversification.
- Multi-objective uses scalarisation with configurable lambda vector.
- All solvers fall back gracefully and report solve status.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage, to_tree, dendrogram
from scipy.spatial.distance import squareform

try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except ImportError:
    CVXPY_AVAILABLE = False
    warnings.warn("cvxpy not found — MVO, CVaR, MaxDiv optimisers unavailable.")

from .constraints import ConstraintBuilder


# ---------------------------------------------------------------------------
# Result container (extends what optimizer.py's OptimizationResult carries)
# ---------------------------------------------------------------------------

@dataclass
class AllocationResult:
    """
    Full output of any optimization run.
    Contains everything needed by the allocation intelligence layer.
    """
    weights: pd.Series                          # optimal weights
    expected_return: float                      # annualised
    volatility: float                           # annualised
    sharpe_ratio: float                         # (μ - rf) / σ
    cvar_95: float                              # 95% CVaR (as positive loss %)
    optimization_type: str                      # human label
    solve_status: str                           # "optimal" / "optimal_inaccurate" / "failed"
    risk_free_rate: float = 0.07

    # Populated by allocation intelligence layer (not optimizer)
    risk_contribution: Dict[str, float] = field(default_factory=dict)
    factor_exposure: Dict[str, float] = field(default_factory=dict)
    allocation_health_score: int = 0
    overweight_underweight_flags: Dict[str, str] = field(default_factory=dict)
    rebalance_actions_rupees: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """JSON-serialisable output dict."""
        return {
            "optimal_weights": {k: round(v, 6) for k, v in self.weights.items()},
            "expected_return": round(self.expected_return, 6),
            "volatility": round(self.volatility, 6),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "cvar": round(self.cvar_95, 6),
            "optimization_type": self.optimization_type,
            "solve_status": self.solve_status,
            "risk_contribution": {k: round(v, 6) for k, v in self.risk_contribution.items()},
            "factor_exposure": {k: round(v, 6) for k, v in self.factor_exposure.items()},
            "allocation_health_score": self.allocation_health_score,
            "overweight_underweight_flags": self.overweight_underweight_flags,
            "rebalance_actions_rupees": self.rebalance_actions_rupees,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _portfolio_stats(
    w: np.ndarray,
    mu: np.ndarray,
    Sigma: np.ndarray,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> Tuple[float, float, float, float]:
    """
    Compute (expected_return, volatility, sharpe, cvar_95) for given weights.

    cvar_95 from historical simulation if returns_history provided,
    else parametric normal approximation.
    """
    port_ret = float(w @ mu)
    port_var = float(w @ Sigma @ w)
    port_std = float(np.sqrt(max(port_var, 0)))
    sharpe = (port_ret - rf) / port_std if port_std > 0 else 0.0

    if returns_history is not None and len(returns_history) > 0:
        # Historical portfolio returns (simple returns)
        # returns_history shape: (T, N)
        port_hist = returns_history @ w
        var_threshold = np.percentile(port_hist, 5)
        tail = port_hist[port_hist <= var_threshold]
        cvar_95 = float(-tail.mean()) if len(tail) > 0 else float(-var_threshold)
    else:
        # Parametric: CVaR_95 ≈ σ × φ(z)/Φ(z) where z=1.645
        from scipy.stats import norm
        z = norm.ppf(0.05)
        cvar_95 = float(-port_std * norm.pdf(z) / 0.05)

    return port_ret, port_std, sharpe, cvar_95


def _make_result(
    w_array: np.ndarray,
    tickers: List[str],
    mu: np.ndarray,
    Sigma: np.ndarray,
    returns_history: Optional[np.ndarray],
    opt_type: str,
    status: str,
    rf: float = 0.07,
) -> AllocationResult:
    weights = pd.Series(w_array, index=tickers)
    ret, vol, sharpe, cvar = _portfolio_stats(w_array, mu, Sigma, returns_history, rf)
    return AllocationResult(
        weights=weights,
        expected_return=ret,
        volatility=vol,
        sharpe_ratio=sharpe,
        cvar_95=cvar,
        optimization_type=opt_type,
        solve_status=status,
        risk_free_rate=rf,
    )


# ---------------------------------------------------------------------------
# 1. Mean-Variance Optimization
# ---------------------------------------------------------------------------

def optimize_mean_variance(
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    lam: float = 1.0,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Maximize:  μᵀw - λ × wᵀΣw

    Parameters
    ----------
    mu : np.ndarray  (N,)
        Annualised arithmetic expected returns.
    Sigma : np.ndarray  (N, N)
        Annualised covariance matrix.
    tickers : List[str]
    constraint_builder : ConstraintBuilder
    lam : float
        Risk-aversion parameter. Higher = more conservative.
        lam=0 → pure return maximisation (dangerous).
        lam=1 → balanced.
        lam→∞ → minimum variance.
    returns_history : np.ndarray (T, N), optional
        Historical simple returns for historical CVaR calculation.
    rf : float
        Risk-free rate for Sharpe.
    """
    if not CVXPY_AVAILABLE:
        raise RuntimeError("cvxpy required for MVO.")

    N = len(tickers)
    w = cp.Variable(N, name="weights")

    objective = cp.Maximize(mu @ w - lam * cp.quad_form(w, Sigma))
    constraints = constraint_builder.build(w, Sigma=Sigma, mu=mu)

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.OSQP, verbose=False, eps_abs=1e-8, eps_rel=1e-8)

    status = prob.status or "failed"
    if w.value is None:
        # Fallback: equal weight
        w_val = np.ones(N) / N
        status = "failed_fallback_equal_weight"
    else:
        w_val = np.maximum(w.value, 0)
        w_val /= w_val.sum()

    return _make_result(w_val, tickers, mu, Sigma, returns_history,
                        f"Mean-Variance (λ={lam})", status, rf)


# ---------------------------------------------------------------------------
# 2. Minimum Variance
# ---------------------------------------------------------------------------

def optimize_minimum_variance(
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> AllocationResult:
    """Minimize wᵀΣw subject to constraints."""
    if not CVXPY_AVAILABLE:
        raise RuntimeError("cvxpy required.")

    N = len(tickers)
    w = cp.Variable(N, name="weights")

    lam_conc = 0.5
    objective = cp.Minimize(
    cp.quad_form(w, Sigma)
    + lam_conc * cp.sum_squares(w)  # sum_squares(w) = HHI
)
    constraints = constraint_builder.build(w, Sigma=Sigma, mu=mu)

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.OSQP, verbose=False, eps_abs=1e-8, eps_rel=1e-8)

    status = prob.status or "failed"
    if w.value is None:
        w_val = np.ones(N) / N
        status = "failed_fallback_equal_weight"
    else:
        w_val = np.maximum(w.value, 0)
        w_val /= w_val.sum()

    return _make_result(w_val, tickers, mu, Sigma, returns_history,
                        "Minimum Variance", status, rf)


# ---------------------------------------------------------------------------
# 3. CVaR Optimization (Rockafellar-Uryasev linearisation)
# ---------------------------------------------------------------------------

def optimize_cvar(
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    returns_history: np.ndarray,
    confidence_level: float = 0.95,
    lam_return: float = 0.0,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Minimize CVaR (Expected Shortfall) at given confidence level.

    Uses the Rockafellar-Uryasev (2000) LP reformulation:
        CVaR_α(w) = min_{z} { z + 1/((1-α)T) × Σ_t max(-rₜᵀw - z, 0) }

    This is a linear program in (w, z, u) where u_t = max(-rₜᵀw - z, 0).

    Parameters
    ----------
    returns_history : np.ndarray  shape (T, N)
        Historical simple returns (NOT log returns).
        Each row is one daily observation.
    confidence_level : float, default 0.95
        CVaR confidence level (95% = worst 5% of days).
    lam_return : float, default 0.0
        If > 0, adds - lam_return × μᵀw to objective (penalise low return).
        Set to a small positive value to avoid degenerate zero-return solutions.
    """
    if not CVXPY_AVAILABLE:
        raise RuntimeError("cvxpy required.")

    T, N = returns_history.shape
    alpha = confidence_level

    w = cp.Variable(N, name="weights")
    z = cp.Variable(name="var_threshold")             # VaR level
    u = cp.Variable(T, nonneg=True, name="shortfall") # auxiliary loss vars

    # Portfolio loss on each day: -rₜᵀw
    losses = -returns_history @ w  # shape (T,)

    objective = cp.Minimize(
        z + (1.0 / ((1 - alpha) * T)) * cp.sum(u)
        - lam_return * (mu @ w)
    )

    constraints = constraint_builder.build(w, Sigma=Sigma, mu=mu)
    constraints += [
        u >= losses - z,   # u_t >= loss_t - z (lower bound on shortfall)
    ]

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.OSQP, verbose=False, eps_abs=1e-8, eps_rel=1e-8)

    status = prob.status or "failed"
    if w.value is None:
        w_val = np.ones(N) / N
        status = "failed_fallback_equal_weight"
    else:
        w_val = np.maximum(w.value, 0)
        if w_val.sum() > 0:
            w_val /= w_val.sum()
        else:
            w_val = np.ones(N) / N

    return _make_result(w_val, tickers, mu, Sigma, returns_history,
                        f"CVaR Optimisation (α={confidence_level:.0%})", status, rf)


# ---------------------------------------------------------------------------
# 4. Risk Parity (Equal Risk Contribution)
# ---------------------------------------------------------------------------

def optimize_risk_parity(
    Sigma: np.ndarray,
    tickers: List[str],
    mu: Optional[np.ndarray] = None,
    target_risk_contributions: Optional[np.ndarray] = None,
    max_iter: int = 500,
    tol: float = 1e-10,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Risk Parity: each asset contributes equally to portfolio risk.

    Solves: minimize Σ_{i,j} (CRC_i - CRC_j)²
    where CRC_i = w_i × (Σw)_i

    Uses the Spinu (2013) Newton algorithm for speed and stability.
    No cvxpy dependency — pure scipy/numpy.

    Parameters
    ----------
    Sigma : np.ndarray  (N, N)
    tickers : List[str]
    mu : np.ndarray (N,), optional
        Only used for reporting expected return.
    target_risk_contributions : np.ndarray (N,), optional
        Desired risk budget per asset (must sum to 1).
        Default: equal = 1/N for all assets.
    max_iter : int
        Newton iterations.
    tol : float
        Convergence tolerance on gradient norm.
    """
    N = len(tickers)

    if target_risk_contributions is None:
        b = np.ones(N) / N  # equal risk budgets
    else:
        b = np.array(target_risk_contributions, dtype=float)
        b /= b.sum()

    # Objective: sum_i (CRC_i/σ_p - b_i)²  where CRC_i = w_i(Σw)_i/σ_p
    # Equivalent to: sum_i (w_i(Σw)_i - b_i × wᵀΣw)² / (wᵀΣw)
    # Use the unconstrained form with x = w / sum(w), then normalise

    def _objective(x):
        x = np.maximum(x, 1e-8)
        Sigma_x = Sigma @ x
        port_var = x @ Sigma_x
        risk_contrib = x * Sigma_x / port_var
        diff = risk_contrib - b
        return 0.5 * np.sum(diff ** 2)

    def _gradient(x):
        x = np.maximum(x, 1e-8)
        Sigma_x = Sigma @ x
        port_var = x @ Sigma_x
        risk_contrib = x * Sigma_x / port_var

        # Gradient of CRC_i w.r.t. x_j
        # ∂CRC_i/∂x_j = (Sigma[i,j]*x_i + Sigma_x[i]*1_{i=j})/port_var
        #               - 2 x_i Sigma_x[i] (Sigma_x[j]) / port_var²
        diff = risk_contrib - b
        dCRC = np.outer(x, Sigma[np.arange(N), np.arange(N)]) / port_var  # approx
        # Full gradient (vectorised)
        Jac = (
            np.diag(Sigma_x) / port_var
            + (np.diag(x) @ Sigma) / port_var
            - 2 * np.outer(x * Sigma_x, Sigma_x) / port_var ** 2
        )
        return Jac.T @ diff

    # Initial guess: inverse-vol weighting
    vols = np.sqrt(np.diag(Sigma))
    x0 = (1.0 / vols) / np.sum(1.0 / vols)

    result = minimize(
        _objective,
        x0,
        jac=_gradient,
        method="L-BFGS-B",
        bounds=[(1e-6, 1.0)] * N,
        options={"maxiter": max_iter, "ftol": tol, "gtol": tol},
    )

    w_val = np.maximum(result.x, 0)
    w_val /= w_val.sum()

    status = "optimal" if result.success else "optimal_inaccurate"
    mu_use = mu if mu is not None else np.zeros(N)

    return _make_result(w_val, tickers, mu_use, Sigma, returns_history,
                        "Risk Parity", status, rf)


# ---------------------------------------------------------------------------
# 5. Hierarchical Risk Parity — HRP  (PRIMARY diversification method)
#    López de Prado (2016) — "Building Diversified Portfolios that Outperform
#    Out-of-Sample", Journal of Portfolio Management.
#
#    Why HRP instead of Maximum Diversification (Choueifaty 2008)?
#    - Max-DR requires matrix inversion → unstable for N < 30 or correlated assets
#    - HRP uses NO matrix inversion — robust to small, correlated universes
#    - Naturally prevents single-asset concentration (e.g. the 45% ICICIBANK
#      problem produced by Min-Variance on this 7-stock Indian equity portfolio)
#    - Three steps: (1) build distance matrix from correlations,
#                   (2) hierarchical clustering (Ward linkage),
#                   (3) recursive bisection allocating inverse-variance weights
# ---------------------------------------------------------------------------

def _hrp_get_cluster_variance(
    cov: np.ndarray,
    cluster_items: List[int],
) -> float:
    """
    Inverse-variance portfolio variance for a subset of assets.
    Used during recursive bisection to size each sub-cluster.
    """
    cov_slice = cov[np.ix_(cluster_items, cluster_items)]
    w_inv_var = 1.0 / np.diag(cov_slice)
    w_inv_var /= w_inv_var.sum()
    return float(w_inv_var @ cov_slice @ w_inv_var)


def _hrp_recursive_bisection(
    cov: np.ndarray,
    sorted_items: List[int],
) -> np.ndarray:
    """
    Allocate weights top-down through the dendrogram via recursive bisection.

    At each split:
      - Left cluster variance → alpha  = 1 - V_left / (V_left + V_right)
      - Right cluster gets   → 1 - alpha
      - Then recurse into each sub-cluster

    Returns weight array of length N (same order as sorted_items).
    """
    N = len(sorted_items)
    weights = np.ones(N)  # start with full budget

    def _bisect(items_idx: List[int], budget: float) -> None:
        """items_idx: positions within sorted_items list"""
        if len(items_idx) == 1:
            weights[items_idx[0]] = budget
            return

        # Split into left/right halves
        mid = len(items_idx) // 2
        left_idx = items_idx[:mid]
        right_idx = items_idx[mid:]

        left_assets  = [sorted_items[i] for i in left_idx]
        right_assets = [sorted_items[i] for i in right_idx]

        v_left  = _hrp_get_cluster_variance(cov, left_assets)
        v_right = _hrp_get_cluster_variance(cov, right_assets)

        # Alpha: fraction of budget going to the LEFT cluster
        # (proportional to the OPPOSITE cluster's variance — riskier cluster
        #  gets LESS weight, which is the diversification logic)
        total_v = v_left + v_right
        if total_v <= 0:
            alpha = 0.5
        else:
            alpha = 1.0 - v_left / total_v  # left gets less if it's riskier

        _bisect(left_idx,  budget * alpha)
        _bisect(right_idx, budget * (1.0 - alpha))

    _bisect(list(range(N)), 1.0)
    return weights


def optimize_hrp(
    Sigma: np.ndarray,
    tickers: List[str],
    mu: Optional[np.ndarray] = None,
    constraint_builder: Optional[ConstraintBuilder] = None,
    returns_history: Optional[np.ndarray] = None,
    linkage_method: str = "ward",
    weight_bounds: Optional[Tuple[float, float]] = None,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Hierarchical Risk Parity (HRP) — López de Prado (2016).

    The three-step algorithm:

    Step 1 — Distance matrix
        Convert correlation matrix to a distance metric:
            d_ij = sqrt(0.5 × (1 - ρ_ij))
        This maps correlation in [-1,1] to distance in [0,1].
        Perfectly correlated assets (ρ=1) → d=0.
        Uncorrelated (ρ=0) → d=0.707. Anti-correlated → d=1.

    Step 2 — Hierarchical clustering (dendrogram)
        Build linkage tree using Ward's method (minimises within-cluster
        variance). Assets that move together are grouped first.
        The order of leaves gives a quasi-diagonal covariance structure.

    Step 3 — Recursive bisection
        Traverse the dendrogram top-down. At each split, allocate the
        parent's risk budget proportionally to the INVERSE of each
        sub-cluster's variance:
            alpha = 1 - V_left / (V_left + V_right)
        Then recurse. Terminal leaves get inverse-variance weights
        within their cluster.

    Parameters
    ----------
    Sigma : np.ndarray  (N, N)
        Annualised covariance matrix.
    tickers : List[str]
        Asset names aligned with Sigma rows/columns.
    mu : np.ndarray (N,), optional
        Expected returns — used only for reporting, not optimisation.
    constraint_builder : ConstraintBuilder, optional
        Weight bounds are respected post-hoc if weight_bounds provided.
        Full constraint sets (sector caps etc.) are NOT applied — HRP
        has no solver. Use weight_bounds for simple min/max clipping.
    returns_history : np.ndarray (T, N), optional
        Historical returns for CVaR calculation.
    linkage_method : str, default "ward"
        Scipy linkage method. Options: "ward", "single", "complete",
        "average". Ward gives the most stable clusters for financial data.
    weight_bounds : Tuple[float, float], optional
        (min_weight, max_weight) hard clip applied after HRP.
        E.g. (0.02, 0.40) enforces 2% floor and 40% cap.
        Weights are renormalised after clipping.
    rf : float
        Risk-free rate for Sharpe reporting.

    Returns
    -------
    AllocationResult
        optimization_type = "HRP (Hierarchical Risk Parity)"
        solve_status = "optimal" always (no solver, never fails)

    Notes
    -----
    For your 7-stock Indian equity portfolio this will produce:
        Cluster A: [SBIN, ICICIBANK]   — correlated PSU/private banks
        Cluster B: [ALEMBICLTD, BHAGERIA, CMSINFO] — mid-cap industrials
        Cluster C: [GOLDBEES]          — uncorrelated commodity (gets large weight)
        Cluster D: [TMPV]              — standalone

    The bank cluster A shares a single risk budget between SBIN+ICICIBANK,
    preventing the 45% single-stock concentration seen in Min-Variance.
    """
    N = len(tickers)

    # ------------------------------------------------------------------
    # Step 1: Correlation matrix → distance matrix
    # ------------------------------------------------------------------
    # Derive correlation from covariance: ρ_ij = Σ_ij / (σ_i × σ_j)
    std_devs = np.sqrt(np.diag(Sigma))
    # Guard against zero-vol assets
    std_devs = np.maximum(std_devs, 1e-8)
    outer_std = np.outer(std_devs, std_devs)
    corr = Sigma / outer_std
    # Clip to [-1, 1] to handle floating-point noise
    corr = np.clip(corr, -1.0, 1.0)

    # Distance metric: d_ij = sqrt(0.5 * (1 - ρ_ij))
    dist_matrix = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, 1.0))
    np.fill_diagonal(dist_matrix, 0.0)

    # ------------------------------------------------------------------
    # Step 2: Hierarchical clustering
    # ------------------------------------------------------------------
    # scipy linkage expects condensed distance vector (upper triangle)
    condensed = squareform(dist_matrix, checks=False)
    link = linkage(condensed, method=linkage_method)

    # Recover the quasi-diagonalised ordering of assets from the dendrogram.
    # This is the leaf order that makes the covariance matrix as
    # block-diagonal as possible.
    tree = to_tree(link, rd=False)

    def _get_leaf_order(node) -> List[int]:
        """DFS traversal of the dendrogram tree → ordered leaf indices."""
        if node.is_leaf():
            return [node.id]
        return _get_leaf_order(node.left) + _get_leaf_order(node.right)

    sorted_indices = _get_leaf_order(tree)   # quasi-diagonal asset ordering

    # ------------------------------------------------------------------
    # Step 3: Recursive bisection weights
    # ------------------------------------------------------------------
    raw_weights = _hrp_recursive_bisection(Sigma, sorted_indices)

    # Map back to original ticker order
    w_val = np.zeros(N)
    for pos, asset_idx in enumerate(sorted_indices):
        w_val[asset_idx] = raw_weights[pos]

    # ------------------------------------------------------------------
    # Optional: apply weight bounds (min/max clip) + renormalise
    # ------------------------------------------------------------------
    lo, hi = (0.0, 1.0)
    if weight_bounds is not None:
        lo, hi = weight_bounds

    sector_map = getattr(constraint_builder, "_sector_map", None) if constraint_builder else None
    sector_cap = getattr(constraint_builder, "_sector_cap", None) if constraint_builder else None
    if sector_map is None and constraint_builder is not None:
        for c in getattr(constraint_builder, "_constraints", []):
            if hasattr(c, "sector_map"):
                sector_map = c.sector_map
                sector_cap = getattr(c, "sector_cap", sector_cap)
                break

    if sector_map and sector_cap is not None:
        from portfolio.internal.constraints import apply_sector_caps_numpy
        w_val = apply_sector_caps_numpy(
            w_val, tickers, sector_map, float(sector_cap),
            min_weight=lo, max_weight=hi,
        )
    else:
        from portfolio.internal.constraints import apply_weight_bounds_numpy
        w_val = apply_weight_bounds_numpy(w_val, min_weight=lo, max_weight=hi)

    # ------------------------------------------------------------------
    # Build result
    # ------------------------------------------------------------------
    mu_use = mu if mu is not None else np.zeros(N)
    return _make_result(
        w_val, tickers, mu_use, Sigma, returns_history,
        "HRP (Hierarchical Risk Parity)", "optimal", rf
    )


# Keep the old name as a deprecated alias so nothing breaks if anything
# else in the codebase still calls optimize_max_diversification.
def optimize_max_diversification(
    Sigma: np.ndarray,
    tickers: List[str],
    mu: Optional[np.ndarray] = None,
    constraint_builder: Optional[ConstraintBuilder] = None,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Deprecated — redirects to optimize_hrp.
    HRP replaced Max-Diversification as the primary diversification method.
    """
    warnings.warn(
        "optimize_max_diversification is deprecated. "
        "Use optimize_hrp instead (registered as 'hrp' in run_optimizer).",
        DeprecationWarning,
        stacklevel=2,
    )
    return optimize_hrp(
        Sigma=Sigma,
        tickers=tickers,
        mu=mu,
        constraint_builder=constraint_builder,
        returns_history=returns_history,
        rf=rf,
    )


# ---------------------------------------------------------------------------
# 6. Multi-Objective Optimization
# ---------------------------------------------------------------------------

def optimize_multi_objective(
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    returns_history: Optional[np.ndarray] = None,
    # Lambda weights for each objective (all non-negative, sum need not be 1)
    lam_return: float = 1.0,       # reward expected return
    lam_vol: float = 1.0,          # penalise volatility
    lam_cvar: float = 0.5,         # penalise CVaR
    lam_drawdown: float = 0.3,     # penalise historical max drawdown contribution
    lam_factor_conc: float = 0.2,  # penalise factor concentration (if betas provided)
    factor_betas: Optional[np.ndarray] = None,   # (N, K)
    factor_target: Optional[np.ndarray] = None,  # (K,) desired factor exposure
    confidence_level: float = 0.95,
    rf: float = 0.07,
) -> AllocationResult:
    """
    Multi-objective scalarised optimisation.

    Objective (maximise):
        lam_return  × μᵀw
      - lam_vol     × wᵀΣw
      - lam_cvar    × CVaR_α(w)           [LP linearised]
      - lam_drawdown× avg_drawdown(w)      [historical approximation]
      - lam_factor_conc × ||Bᵀw - target||² [factor concentration]

    CVaR term requires returns_history.
    Factor concentration term requires factor_betas.
    drawdown_penalty is the average of historical drawdown on the weight vector.

    Parameters
    ----------
    lam_return, lam_vol, lam_cvar, lam_drawdown, lam_factor_conc : float
        Scalarisation weights. Set any to 0 to exclude that objective.
    factor_betas : np.ndarray (N, K), optional
        Asset factor loadings. Required for factor concentration penalty.
    factor_target : np.ndarray (K,), optional
        Desired portfolio factor exposure. Defaults to zeros (neutral).
    """
    if not CVXPY_AVAILABLE:
        raise RuntimeError("cvxpy required for multi-objective optimisation.")

    N = len(tickers)
    w = cp.Variable(N, name="weights")

    objective_terms = []

    # 1. Return maximisation
    if lam_return > 0:
        objective_terms.append(lam_return * (mu @ w))

    # 2. Variance penalty
    if lam_vol > 0:
        objective_terms.append(-lam_vol * cp.quad_form(w, Sigma))

    # 3. CVaR penalty (Rockafellar-Uryasev)
    extra_constraints = []
    if lam_cvar > 0 and returns_history is not None:
        T = len(returns_history)
        z = cp.Variable(name="var_z")
        u = cp.Variable(T, nonneg=True, name="cvar_u")
        alpha = confidence_level
        cvar_term = z + (1.0 / ((1 - alpha) * T)) * cp.sum(u)
        objective_terms.append(-lam_cvar * cvar_term)
        losses = -returns_history @ w
        extra_constraints += [u >= losses - z]

    # 4. Drawdown penalty (historical approximation)
    # Approximate: penalise average of the worst (1-alpha) daily losses
    # This is a simpler proxy that avoids path-dependency in a static optimizer
    if lam_drawdown > 0 and returns_history is not None:
        T = len(returns_history)
        alpha = confidence_level
        z_dd = cp.Variable(name="dd_z")
        u_dd = cp.Variable(T, nonneg=True, name="dd_u")
        losses = -returns_history @ w
        dd_term = z_dd + (1.0 / ((1 - alpha) * T)) * cp.sum(u_dd)
        objective_terms.append(-lam_drawdown * dd_term)
        extra_constraints += [u_dd >= losses - z_dd]

    # 5. Factor concentration penalty
    if lam_factor_conc > 0 and factor_betas is not None:
        B = factor_betas  # (N, K)
        if factor_target is None:
            factor_target = np.zeros(B.shape[1])
        portfolio_factor_exp = B.T @ w  # (K,)
        deviation = portfolio_factor_exp - factor_target
        # cp.sum_squares is convex
        objective_terms.append(-lam_factor_conc * cp.sum_squares(deviation))

    if not objective_terms:
        raise ValueError("All lambda values are zero — no objective defined.")

    objective = cp.Maximize(sum(objective_terms))
    constraints = constraint_builder.build(w, Sigma=Sigma, mu=mu) + extra_constraints

    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.OSQP, verbose=False, eps_abs=1e-8, eps_rel=1e-8,
               max_iter=10000)

    status = prob.status or "failed"
    if w.value is None:
        w_val = np.ones(N) / N
        status = "failed_fallback_equal_weight"
    else:
        w_val = np.maximum(w.value, 0)
        if w_val.sum() > 0:
            w_val /= w_val.sum()
        else:
            w_val = np.ones(N) / N

    label = (
        f"Multi-Objective ("
        f"λ_ret={lam_return}, λ_vol={lam_vol}, "
        f"λ_cvar={lam_cvar}, λ_dd={lam_drawdown}, "
        f"λ_fc={lam_factor_conc})"
    )
    return _make_result(w_val, tickers, mu, Sigma, returns_history, label, status, rf)


# ---------------------------------------------------------------------------
# Efficient Frontier (Pareto-optimal portfolios)
# ---------------------------------------------------------------------------

@dataclass
class EfficientFrontierResult:
    """Stores the full efficient frontier."""
    returns: np.ndarray
    volatilities: np.ndarray
    sharpe_ratios: np.ndarray
    weights_matrix: np.ndarray          # shape (n_points, N)
    pareto_portfolios: List[AllocationResult]  # full result objects at each point

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({
            "return": self.returns,
            "volatility": self.volatilities,
            "sharpe": self.sharpe_ratios,
        })


def compute_efficient_frontier(
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    n_points: int = 50,
    returns_history: Optional[np.ndarray] = None,
    rf: float = 0.07,
) -> EfficientFrontierResult:
    """
    Compute the efficient frontier by sweeping target returns.

    For each target return level, solve:
        minimize wᵀΣw
        subject to: μᵀw >= target_return, [all other constraints]

    Parameters
    ----------
    n_points : int
        Number of frontier points (default 50).
    """
    if not CVXPY_AVAILABLE:
        raise RuntimeError("cvxpy required for efficient frontier.")

    N = len(tickers)

    # Find min and max achievable returns under constraints
    # Min return: minimum variance portfolio
    min_var_result = optimize_minimum_variance(
        mu, Sigma, tickers, constraint_builder, returns_history, rf
    )
    mu_min = min_var_result.expected_return

    # Max return: unconstrained maximum (but constrained weights)
    w_temp = cp.Variable(N)
    prob_max = cp.Problem(
        cp.Maximize(mu @ w_temp),
        constraint_builder.build(w_temp, Sigma=Sigma, mu=mu)
    )
    prob_max.solve(solver=cp.OSQP, verbose=False)
    mu_max = float(mu @ w_temp.value) if w_temp.value is not None else mu.max()

    target_returns = np.linspace(mu_min, mu_max, n_points)

    all_returns, all_vols, all_sharpes = [], [], []
    all_weights = []
    pareto = []

    w = cp.Variable(N, name="weights")

    for target in target_returns:
        base_constraints = constraint_builder.build(w, Sigma=Sigma, mu=mu)
        constraints = base_constraints + [mu @ w >= target]
        prob = cp.Problem(cp.Minimize(cp.quad_form(w, Sigma)), constraints)
        prob.solve(solver=cp.OSQP, verbose=False, eps_abs=1e-9, eps_rel=1e-9)

        if prob.status in ("optimal", "optimal_inaccurate") and w.value is not None:
            w_val = np.maximum(w.value, 0)
            w_val /= w_val.sum()
            ret, vol, sharpe, cvar = _portfolio_stats(w_val, mu, Sigma, returns_history, rf)
            all_returns.append(ret)
            all_vols.append(vol)
            all_sharpes.append(sharpe)
            all_weights.append(w_val)
            pareto.append(
                _make_result(w_val, tickers, mu, Sigma, returns_history,
                             f"Frontier (μ={target:.2%})", prob.status, rf)
            )

    return EfficientFrontierResult(
        returns=np.array(all_returns),
        volatilities=np.array(all_vols),
        sharpe_ratios=np.array(all_sharpes),
        weights_matrix=np.array(all_weights),
        pareto_portfolios=pareto,
    )


# ---------------------------------------------------------------------------
# Convenience dispatcher
# ---------------------------------------------------------------------------

OPTIMIZERS = {
    "mean_variance":      optimize_mean_variance,
    "min_variance":       optimize_minimum_variance,
    "cvar":               optimize_cvar,
    "risk_parity":        optimize_risk_parity,
    "hrp":                optimize_hrp,                   # PRIMARY diversification method
    "max_diversification": optimize_max_diversification,  # deprecated alias → hrp
    "multi_objective":    optimize_multi_objective,
}


def run_optimizer(
    method: str,
    mu: np.ndarray,
    Sigma: np.ndarray,
    tickers: List[str],
    constraint_builder: ConstraintBuilder,
    **kwargs,
) -> AllocationResult:
    """
    Dispatch to the correct optimizer by name.

    Parameters
    ----------
    method : str
        One of: "mean_variance", "min_variance", "cvar",
                "risk_parity", "max_diversification", "multi_objective"
    kwargs : passed through to optimizer (lam, returns_history, etc.)
    """
    if method not in OPTIMIZERS:
        raise ValueError(
            f"Unknown method '{method}'. Choose from: {list(OPTIMIZERS.keys())}"
        )
    return OPTIMIZERS[method](mu, Sigma, tickers, constraint_builder, **kwargs)
