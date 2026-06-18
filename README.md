# ClearView Analytics: Institutional Risk & Intelligence Engine

[![Vercel Deployment](https://img.shields.io/badge/Deployment-Live-success?style=flat-square&logo=vercel)](https://clearview-analytics-prod.vercel.app)
[![Tech Stack](https://img.shields.io/badge/Stack-FastAPI%20%7C%20Vanilla%20JS%20%7C%20Python-blue?style=flat-square)](https://fastapi.tiangolo.com/)

**ClearView Analytics** is a high-fidelity quantitative finance platform designed for institutional-grade portfolio optimization, regime-switching intelligence, and multi-scenario risk management.

---

## Key Capabilities

### Quantitative Intelligence
- **Regime-Switching Engine (M7):** Advanced Hidden Markov Models (HMM) coupled with GARCH(1,1) filters to detect market shifts and modulate risk and allocation dynamically.
- **Institutional Optimizer (M5):** Robust Black-Litterman and Hierarchical Risk Parity (HRP) allocation for sophisticated multi-asset portfolios.
- **Stress Testing (M4):** Macroeconomic scenario analysis with beta-propagated shocks covering inflation spikes, rate hikes, and crisis scenarios.
- **Performance & Risk (M3):** Efficient frontier, VaR/CVaR, drawdown, and factor (CAPM) decomposition.

---

## Tech Stack & Architecture

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11)
- **Frontend:** Pure Vanilla JS & CSS for maximum performance and a premium "Glassmorphism" aesthetic.
- **Libraries:** `NumPy`, `Pandas`, `SciPy`, `CVXPY`, `hmmlearn`, `Statsmodels`.
- **Cloud Infrastructure:** [Vercel](https://vercel.com/) (Serverless Lambda deployment).

---

## Local Setup

1. **Clone & Explore:**
   ```bash
   git clone https://github.com/Sumeru-M/New-folder-master.git
   cd New-folder-master
   ```

2. **Environment Ready:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ignite the Engine:**
   ```bash
   uvicorn src.main:app --reload
   ```
   Access the cockpit at `http://localhost:8000`.

---

## Cloud Deployment

The platform is fully optimized for **Vercel** via `app.py` and `vercel.json`.

### Required Environment Variables:
| Variable | Description |
|----------|-------------|
| `AUTH_SECRET` | Secure JWT key for the integrated identity system. |
| `AUTH_DB_PATH` | Path to the SQLite auth DB. On Render, point this at a persistent disk (e.g. `/var/data/clearview_auth.db`) so accounts survive restarts. Ignored when Supabase is configured. |
| `SUPABASE_URL` | Supabase project URL for persistent login storage. |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key used by the backend auth API. |
| `SUPABASE_USERS_TABLE` | Optional users table name. Defaults to `users`. |
| `CORS_ORIGINS` | Permitted domains for cross-origin resource sharing. |

Run `docs/supabase_auth.sql` in the Supabase SQL editor before deploying auth.

---

## Repository Structure
- `src/`: Core FastAPI server and business logic.
- `portfolio/`: High-performance quantitative engines (M3–M7).
- `frontend/`: Institutional-grade, terminal-inspired analytics UI (single-file React).
- `docs/`: Expanded technical documentation and research notebooks.

---

Developed with precision for institutional risk management. **View the live demo:** [clearview-analytics-prod.vercel.app](https://clearview-analytics-prod.vercel.app)

## Disclaimer
This project is for educational and research purposes only.

-Not intended for real trading or investment.
-No investment advice or guarantees provided.
-Creator assumes no liability for financial losses.
-Consult a financial advisor for investment decisions.
-Past performance does not indicate future results.
-By using this software, you agree to use it solely for learning purposes.
