"""
Smoke tests for auth, price preprocessing, and HRP registration.
Run: python -m pytest tests/test_core_fixes.py -v
Or:  python tests/test_core_fixes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_auth_register_login_sqlite():
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test_users.db"
    os.environ["AUTH_DB_PATH"] = str(db_path)

    import importlib
    import src.main as main

    importlib.reload(main)

    username = f"testuser_{int(time.time())}"
    email = f"{username}@example.com"
    password = "testpass123"

    reg = main.auth_register(
        main.AuthRegisterRequest(username=username, email=email, password=password)
    )
    assert reg.status_code == 201
    body = reg.body.decode()
    assert "token" in body

    row = main._get_user_by_username(username)
    assert row is not None
    assert main._verify_password(password, str(main._row_get(row, "password_hash")))

    login = main.auth_login(main.AuthLoginRequest(username=username, password=password))
    assert login.status_code == 200
    login_body = login.body.decode()
    assert "token" in login_body


def test_prepare_price_panel_overlap():
    from portfolio.price_preprocessing import prepare_price_panel

    idx = pd.date_range("2020-01-01", periods=120, freq="B")
    prices = pd.DataFrame(
        {
            "A.NS": np.linspace(100, 130, len(idx)),
            "B.NS": np.linspace(200, 240, len(idx)),
            "C.NS": [np.nan] * 80 + list(np.linspace(50, 60, len(idx) - 80)),
        },
        index=idx,
    )
    aligned, diag = prepare_price_panel(prices, ["A.NS", "B.NS", "C.NS"])
    assert "A.NS" in aligned.columns
    assert "B.NS" in aligned.columns
    assert len(aligned) >= 60
    assert diag["valid_tickers"]


def test_hrp_optimizer_registered():
    from portfolio.internal.optimization_engine import OPTIMIZERS, optimize_hrp

    assert "hrp" in OPTIMIZERS
    N = 4
    tickers = [f"T{i}.NS" for i in range(N)]
    rng = np.random.default_rng(42)
    R = rng.standard_normal((200, N)) * 0.01
    Sigma = np.cov(R.T) * 252
    res = optimize_hrp(Sigma=Sigma, tickers=tickers, weight_bounds=(0.05, 0.40))
    assert abs(res.weights.sum() - 1.0) < 1e-6
    assert all(0.05 - 1e-6 <= w <= 0.40 + 1e-6 for w in res.weights.values)


def test_health_endpoints():
    import importlib
    import src.main as main

    importlib.reload(main)
    h = main.health()
    assert h["status"] == "ok"
    ready = main.health_ready()
    assert ready.status_code in (200, 503)


if __name__ == "__main__":
    test_auth_register_login_sqlite()
    print("auth OK")
    test_prepare_price_panel_overlap()
    print("price preprocessing OK")
    test_hrp_optimizer_registered()
    print("hrp OK")
    test_health_endpoints()
    print("health OK")
    print("All smoke tests passed.")
