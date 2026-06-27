import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from portfolio.api_m3 import get_portfolio_construction
from portfolio.api_m4 import get_scenario_analysis
from portfolio.api_m5 import get_institutional_optimisation
from portfolio.api_m7 import get_market_regime


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_FILE = ROOT_DIR / "frontend" / "index.html"

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("clearview.api")

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
    conn = sqlite3.connect(path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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


def _parse_supabase_error(raw_detail: str) -> tuple[int, str]:
    """Map PostgREST errors to HTTP status codes."""
    try:
        payload = json.loads(raw_detail)
        if isinstance(payload, dict):
            code = str(payload.get("code", ""))
            message = str(payload.get("message", raw_detail))
            if code == "23505":
                return 409, "That username or email is already registered."
            return 502, message
        if isinstance(payload, list) and payload:
            code = str(payload[0].get("code", ""))
            message = str(payload[0].get("message", raw_detail))
            if code == "23505":
                return 409, "That username or email is already registered."
            return 502, message
    except json.JSONDecodeError:
        pass
    if "duplicate key" in raw_detail.lower() or "23505" in raw_detail:
        return 409, "That username or email is already registered."
    return 502, f"Database error: {raw_detail[:500]}"


def _supabase_request(path: str, method: str = "GET", body: bytes | None = None) -> Any:
    prefer = "return=representation" if method == "POST" else None
    extra_headers: dict[str, str] = {}
    if prefer:
        extra_headers["Prefer"] = prefer
    elif method != "GET":
        extra_headers["Prefer"] = "return=minimal"

    req = Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=body,
        method=method,
        headers=_supabase_headers(extra_headers or None),
    )
    try:
        with urlopen(req, timeout=12) as res:
            raw = res.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        status, message = _parse_supabase_error(detail)
        logger.error("Supabase %s %s failed (%s): %s", method, path, exc.code, message)
        raise HTTPException(status_code=status, detail=message) from exc
    except URLError as exc:
        logger.error("Supabase unreachable: %s", exc.reason)
        raise HTTPException(status_code=502, detail=f"Database unreachable: {exc.reason}") from exc
    if not raw:
        return None
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


def _sb_insert_user(username: str, email: str, password_hash: str, now: int) -> dict[str, Any]:
    payload = {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "created_at": now,
        "updated_at": now,
    }
    rows = _supabase_request(
        SUPABASE_USERS_TABLE,
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
    )
    if isinstance(rows, list) and rows:
        return rows[0]
    return payload


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


app = FastAPI(title="ClearView Analytics API", version="1.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Unhandled error on %s %s (%.0fms)",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


def _auth_storage_health() -> dict[str, Any]:
    info: dict[str, Any] = {
        "backend": "supabase" if _using_supabase() else "sqlite",
        "ok": False,
        "detail": "",
    }
    try:
        if _using_supabase():
            _supabase_request(f"{SUPABASE_USERS_TABLE}?select=username&limit=1")
            info["ok"] = True
            info["detail"] = "Supabase reachable"
        else:
            with _db_connect() as conn:
                conn.execute("SELECT 1 FROM users LIMIT 1")
            info["ok"] = True
            info["detail"] = f"SQLite at {_auth_db_path()}"
    except HTTPException as exc:
        info["detail"] = str(exc.detail)
    except Exception as exc:
        info["detail"] = str(exc)
    return info


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
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "auth_storage": _auth_storage_health()["backend"],
    }


@app.get("/api/health/ready")
def health_ready() -> JSONResponse:
    auth_h = _auth_storage_health()
    ready = auth_h["ok"]
    body = {
        "status": "ready" if ready else "degraded",
        "checks": {"auth_storage": auth_h},
        "timestamp": int(time.time()),
    }
    return JSONResponse(content=body, status_code=200 if ready else 503)


@app.get("/api/auth/config")
def auth_config() -> JSONResponse:
    return _safe_json(
        {
            "auth_mode": "jwt_username_password",
            "storage": "supabase" if _using_supabase() else "sqlite",
            "configured": True,
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
    try:
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
    except sqlite3.IntegrityError:
        return _safe_json({"error": "That username or email is already registered."}, status_code=409)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Registration failed for %s", username)
        return _safe_json({"error": f"Registration failed: {exc}"}, status_code=500)

    stored = _get_user_by_username(username)
    if not stored or not _row_get(stored, "password_hash"):
        logger.error("User %s not found after registration commit", username)
        return _safe_json(
            {"error": "Account was not persisted. Check server storage configuration."},
            status_code=500,
        )

    token = _make_token(username)
    logger.info("Registered user %s (storage=%s)", username, _auth_storage_health()["backend"])
    return _safe_json(
        {
            "message": "Account created successfully.",
            "token": token,
            "user": {
                "username": username,
                "email": email,
                "created_at": now,
            },
        },
        status_code=201,
    )


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
        logger.exception("M3 optimize failed")
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
        logger.exception("M4 scenarios failed")
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
        logger.exception("M5 institutional failed")
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
        # The UI is a single in-place HTML file. Disable caching so edits/redeploys
        # are picked up on the next load instead of serving a stale cached page.
        return FileResponse(
            FRONTEND_FILE,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return JSONResponse({"message": "Frontend file not found. Expected frontend/index.html"})


@app.get("/app")
def serve_frontend_app():
    return serve_frontend()
