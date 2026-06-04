import os
import re
import sqlite3
# Fresh commit for Vercel deployment: 2026-04-08T16:17:30Z
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from portfolio.api_m3 import get_portfolio_construction
from portfolio.api_m4 import get_scenario_analysis
from portfolio.api_m5 import get_institutional_optimisation
from portfolio.api_m6 import get_security_attack_test, get_virtual_trade_and_security
from portfolio.api_m7 import get_market_regime


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_FILE = ROOT_DIR / "frontend" / "index.html"

AUTH_ALGORITHM = "HS256"
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "604800"))  # 7 days
AUTH_SECRET = os.getenv("AUTH_SECRET", "change-this-dev-secret").strip() or "change-this-dev-secret"
AUTH_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_USERS_TABLE = os.getenv("SUPABASE_USERS_TABLE", "users").strip() or "users"


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "*")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"]


def _auth_db_path() -> Path:
    explicit = os.getenv("AUTH_DB_PATH", "").strip()
    if explicit:
        return Path(explicit)
    if os.getenv("VERCEL"):
        return Path("/tmp/clearview_auth.db")
    return ROOT_DIR / "artifacts" / "auth" / "users.db"


def _db_connect() -> sqlite3.Connection:
    path = _auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _using_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _supabase_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        **(extra or {}),
    }


def _supabase_request(path: str, method: str = "GET", body: bytes | None = None) -> Any:
    req = Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=body,
        method=method,
        headers=_supabase_headers({"Prefer": "return=minimal"} if method != "GET" else None),
    )
    try:
        with urlopen(req, timeout=12) as res:
            raw = res.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"Supabase error: {detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Supabase unreachable: {exc.reason}") from exc
    if not raw:
        return None
    import json

    return json.loads(raw)


def _sb_eq(value: str) -> str:
    return quote(f"eq.{value}", safe="")


def _sb_select_user(column: str, value: str) -> dict[str, Any] | None:
    if not _using_supabase():
        return None
    cols = "username,email,created_at,updated_at,password_hash"
    rows = _supabase_request(
        f"{SUPABASE_USERS_TABLE}?{column}={_sb_eq(value)}&select={cols}&limit=1"
    )
    return rows[0] if rows else None


def _sb_insert_user(username: str, email: str, password_hash: str, now: int) -> None:
    import json

    payload = {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "created_at": now,
        "updated_at": now,
    }
    _supabase_request(
        SUPABASE_USERS_TABLE,
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
    )


def _init_auth_db() -> None:
    if _using_supabase():
        return
    with _db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        cols = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "username" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
            existing = conn.execute(
                "SELECT id, email FROM users WHERE username IS NULL OR username = ''"
            ).fetchall()
            taken = {
                str(row[0])
                for row in conn.execute(
                    "SELECT username FROM users WHERE username IS NOT NULL AND username <> ''"
                ).fetchall()
            }
            for row in existing:
                user_id = int(row[0])
                email = str(row[1] or "")
                base = _normalize_username(email.split("@")[0])
                base = re.sub(r"[^a-z0-9_.-]+", "", base)
                if not base:
                    base = f"user{user_id}"
                candidate = base[:40]
                suffix = 1
                while candidate in taken:
                    candidate = f"{base[:34]}_{suffix}"
                    suffix += 1
                taken.add(candidate)
                conn.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (candidate, user_id),
                )

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        conn.commit()


def _normalize_username(raw: str) -> str:
    return str(raw or "").strip().lower()


def _normalize_email(raw: str) -> str:
    return str(raw or "").strip().lower()


def _valid_username(username: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", username))


def _valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]


def _hash_password(password: str) -> str:
    return AUTH_PWD_CONTEXT.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return AUTH_PWD_CONTEXT.verify(password, password_hash)
    except Exception:
        return False


def _make_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=AUTH_TOKEN_TTL_SECONDS)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, AUTH_SECRET, algorithm=AUTH_ALGORITHM)


def _parse_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, AUTH_SECRET, algorithms=[AUTH_ALGORITHM])
        username = _normalize_username(payload.get("sub", ""))
        if not username:
            raise HTTPException(status_code=401, detail="Unauthorized: token subject missing")
        return payload
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Unauthorized: token expired") from exc
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid token") from exc


def _get_user_by_username(username: str) -> Any | None:
    if _using_supabase():
        return _sb_select_user("username", username)
    with _db_connect() as conn:
        row = conn.execute(
            "SELECT username, email, created_at, updated_at, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row


def _get_user_by_email(email: str) -> Any | None:
    if _using_supabase():
        return _sb_select_user("email", email)
    with _db_connect() as conn:
        row = conn.execute(
            "SELECT username, email, created_at, updated_at, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return row


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _auth_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized: missing Authorization header")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Unauthorized: use Bearer token")

    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: empty bearer token")

    payload = _parse_token(token)
    username = _normalize_username(payload.get("sub", ""))
    if not _get_user_by_username(username):
        raise HTTPException(status_code=401, detail="Unauthorized: user not found")
    return username


def _safe_json(result: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=result, status_code=status_code)


def _normalize_transaction_for_security(transaction: dict[str, Any]) -> dict[str, Any]:
    tx = dict(transaction or {})
    if "verification_status" not in tx and "verified" in tx:
        tx["verification_status"] = bool(tx["verified"])
    tx.setdefault("verification_status", True)
    tx.setdefault("signed_at", time.time())
    tx.setdefault("tx_id", f"TX_{int(time.time() * 1000)}")
    tx.setdefault("sha3_hash", "0" * 64)
    tx.setdefault("signature", {"scheme": "ML-DSA-III"})
    return tx


ATTACK_TYPE_MAP = {
    "adversarial_evasion": "signature_forgery",
    "sybil_trust_poisoning": "burst",
    "model_extraction": "weak_hash",
    "side_channel_timing_leaks": "replay",
    "side_channel_timing": "replay",
    "fault_injection": "combined",
    "triangular_fraud": "burst",
    "price_oracle_manipulation": "weak_hash",
    "front_running_sandwich_attack": "replay",
    "front_running": "replay",
}


app = FastAPI(title="ClearView Analytics API", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_init_auth_db()


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=8, max_length=128)


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class M3Request(BaseModel):
    tickers: list[str]
    current_weights: list[float] | None = None
    period: str = "2y"
    risk_free_rate: float = 0.07


class M4Request(BaseModel):
    tickers: list[str]
    current_weights: list[float] | None = None
    portfolio_value: float = 1_000_000
    risk_free_rate: float = 0.07
    confidence_level: float = 0.95
    scenarios: str = "ALL"


class M5Request(BaseModel):
    tickers: list[str]
    current_weights: list[float] | None = None
    portfolio_value: float = 1_000_000
    risk_free_rate: float = 0.07
    max_weight: float = 0.40
    sector_cap: float = 0.60
    confidence_level: float = 0.95
    methods: str = "all"


class M6SimulateRequest(BaseModel):
    ticker: str
    quantity: float
    price: float
    holdings: dict[str, float]
    current_prices: dict[str, float]
    total_value: float
    risk_free_rate: float = 0.07
    n_mc_paths: int = 1_000


class M6SecurityTestRequest(BaseModel):
    transaction: dict[str, Any]
    attack_type: str


class M7Request(BaseModel):
    tickers: list[str]
    risk_free_rate: float = 0.07
    horizons: list[int] = Field(default_factory=lambda: [21, 63])
    risk_appetite: str = "balanced"
    hmm_restarts: int = 3
    hmm_max_iter: int = 150
    garch_n_sim: int = 300
    uncertainty_n_boot: int = 200


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/config")
def auth_config() -> JSONResponse:
    return _safe_json(
        {
            "auth_mode": "jwt_username_password",
            "storage": "supabase" if _using_supabase() else "sqlite",
            "configured": _using_supabase() or True,
            "message": "Username and password authentication is enabled.",
        }
    )


@app.post("/api/auth/register")
def auth_register(req: AuthRegisterRequest) -> JSONResponse:
    username = _normalize_username(req.username)
    email = _normalize_email(req.email)
    password = req.password

    if not _valid_username(username):
        return _safe_json(
            {"error": "Username must be 3-50 characters using letters, numbers, dot, underscore, or hyphen."},
            status_code=400,
        )
    if not _valid_email(email):
        return _safe_json({"error": "Please enter a valid email address."}, status_code=400)
    if len(password) < 8:
        return _safe_json({"error": "Password must be at least 8 characters."}, status_code=400)

    if _get_user_by_username(username):
        return _safe_json({"error": "That username is already taken."}, status_code=409)

    if _get_user_by_email(email):
        return _safe_json({"error": "That email is already registered."}, status_code=409)

    now = int(time.time())
    password_hash = _hash_password(password)
    if _using_supabase():
        _sb_insert_user(username, email, password_hash, now)
    else:
        with _db_connect() as conn:
            cols = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "full_name" in cols:
                conn.execute(
                    "INSERT INTO users(username, email, full_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, email, username, password_hash, now, now),
                )
            else:
                conn.execute(
                    "INSERT INTO users(username, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (username, email, password_hash, now, now),
                )
            conn.commit()

    return _safe_json({"message": "Account created successfully."}, status_code=201)


@app.post("/api/auth/login")
def auth_login(req: AuthLoginRequest) -> JSONResponse:
    identifier = _normalize_username(req.username)
    row = _get_user_by_email(identifier) if "@" in identifier else _get_user_by_username(identifier)
    if not row and "@" not in identifier:
        row = _get_user_by_email(identifier)
    if not row or not _verify_password(req.password, str(_row_get(row, "password_hash", ""))):
        return _safe_json({"error": "Username or password is incorrect."}, status_code=401)

    username = str(_row_get(row, "username", identifier))
    token = _make_token(username)
    return _safe_json(
        {
            "token": token,
            "user": {
                "username": username,
                "email": str(_row_get(row, "email", "")),
                "created_at": int(_row_get(row, "created_at", 0) or 0),
            },
        }
    )


@app.get("/api/auth/me")
def auth_me(username: str = Depends(_auth_user)) -> JSONResponse:
    row = _get_user_by_username(username)
    if not row:
        return _safe_json({"error": "User not found."}, status_code=404)
    return _safe_json(
        {
            "user": {
                "username": str(_row_get(row, "username", "")),
                "email": str(_row_get(row, "email", "")),
                "created_at": int(_row_get(row, "created_at", 0) or 0),
            }
        }
    )


@app.post("/api/m3/optimize")
def m3_optimize(req: M3Request, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        result = get_portfolio_construction(
            tickers=req.tickers,
            current_weights=req.current_weights,
            period=req.period,
            risk_free_rate=req.risk_free_rate,
        )
        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.post("/api/m4/scenarios")
def m4_scenarios(req: M4Request, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        result = get_scenario_analysis(
            tickers=req.tickers,
            current_weights=req.current_weights,
            portfolio_value=req.portfolio_value,
            risk_free_rate=req.risk_free_rate,
            confidence_level=req.confidence_level,
            scenarios=req.scenarios,
        )
        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.post("/api/m5/institutional")
def m5_institutional(req: M5Request, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        result = get_institutional_optimisation(
            tickers=req.tickers,
            current_weights=req.current_weights,
            portfolio_value=req.portfolio_value,
            risk_free_rate=req.risk_free_rate,
            max_weight=req.max_weight,
            sector_cap=req.sector_cap,
            confidence_level=req.confidence_level,
            methods=req.methods,
        )
        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.post("/api/m6/simulate")
def m6_simulate(req: M6SimulateRequest, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        result = get_virtual_trade_and_security(
            ticker=req.ticker,
            quantity=req.quantity,
            price=req.price,
            holdings=req.holdings,
            current_prices=req.current_prices,
            total_value=req.total_value,
            risk_free_rate=req.risk_free_rate,
            n_mc_paths=max(1000, int(req.n_mc_paths)),
        )

        tx = result.get("transaction") or {}
        if tx:
            tx.setdefault("verification_status", tx.get("verified", True))
            tx.setdefault("signed_at", time.time())
            result["transaction"] = tx

        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.post("/api/m6/security/test")
def m6_security_test(req: M6SecurityTestRequest, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        attack_type = ATTACK_TYPE_MAP.get(req.attack_type, req.attack_type)
        tx = _normalize_transaction_for_security(req.transaction)
        result = get_security_attack_test(transaction=tx, attack_type=attack_type)
        result["requested_attack_type"] = req.attack_type
        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.post("/api/m7/regime")
def m7_regime(req: M7Request, _username: str = Depends(_auth_user)) -> JSONResponse:
    try:
        result = get_market_regime(
            tickers=req.tickers,
            risk_free_rate=req.risk_free_rate,
            horizons=req.horizons,
            risk_appetite=req.risk_appetite,
            hmm_restarts=req.hmm_restarts,
            hmm_max_iter=req.hmm_max_iter,
            garch_n_sim=req.garch_n_sim,
            uncertainty_n_boot=req.uncertainty_n_boot,
        )
        return _safe_json(result)
    except Exception as exc:  # pragma: no cover
        return _safe_json({"error": str(exc)})


@app.get("/")
def serve_frontend():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)
    return JSONResponse({"message": "Frontend file not found. Expected frontend/index.html"})


@app.get("/app")
def serve_frontend_app():
    return serve_frontend()
