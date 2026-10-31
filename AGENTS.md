# BizNexa contributor guidance

## Actual architecture

BizNexa currently uses a React 19 + TypeScript + Vite frontend in `frontend/` and a FastAPI backend in `backend/`. The backend uses SQLAlchemy with psycopg for PostgreSQL access and Alembic for migrations. The existing `frontend/src/App.tsx` remains the navigation shell and preserves the Graphite & Copper visual system; API requests are centralized in `frontend/src/services/api.ts`.

The server exposes `/health`, `/health/db`, and read-only analytics endpoints under `/api/analytics/synthetic/*`. Routes and database access live in the FastAPI application and analytics service module. Avoid creating a second frontend or backend project when extending this codebase.

## Environment and Supabase

- Keep the real `DATABASE_URL` in a local root `.env` or `backend/.env`; it is server-only and must never be imported by React, logged, or returned by an API.
- Copy the root `.env.example` to `.env` and set the Supabase PostgreSQL connection string. A Supabase Session Pooler URL is generally the most reliable choice for local IPv4 environments.
- The backend accepts Supabase's generic `postgresql://` URI and normalizes it to `postgresql+psycopg://`; URL-encode special password characters.
- The frontend may use optional `VITE_API_BASE_URL` in `frontend/.env`; local Vite development binds to `127.0.0.1` and uses the proxy in `frontend/vite.config.ts` by default. Never put database credentials in any `VITE_*` variable.
- A database is considered connected only after the backend executes a real query. Startup does not import or reset data.
- Synthetic data is development-only. The API reads the schema named by `ANALYTICS_SCHEMA` (default `public` for manually imported Supabase tables); the explicit loader uses the isolated `biznexa_synthetic` schema when rebuilding development data.

## Local commands

From the repository root:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
npm --prefix frontend run build

.venv\\Scripts\\python.exe -m pip install -e .
$env:PYTHONPATH = 'D:\\Project\\BizNexa\\backend'
.venv\\Scripts\\python.exe -m uvicorn biznexa.main:app --host 127.0.0.1 --port 8000
.venv\\Scripts\\python.exe -m pytest -q
.venv\\Scripts\\python.exe -m ruff check backend
.venv\\Scripts\\python.exe backend/scripts/seed_synthetic.py
.venv\\Scripts\\python.exe backend/scripts/seed_synthetic.py --load
```

The validation command writes `reports/synthetic-data-validation.json`. The load command requires `SYNTHETIC_LOAD_ENABLED=true`, a reachable `DATABASE_URL`, and the source package at `backend/biznexa_data/`. Do not run it against production data.

## Engineering rules

- Keep routes, services, repositories, and presentation code separate as the code grows; use parameterized SQL and input validation.
- Do not hardcode business metrics or silently fall back to fake data when an API request fails. Synthetic values must be labeled as synthetic and sourced from the backend.
- Preserve financial precision, foreign-key relationships, historical records, and the documented KPI definitions.
- Do not expose secrets, commit local `.env` files, or claim a database, import, test, or build succeeded without running it.
- Remove only generated or demonstrably unused files after checking references. Preserve migrations, schemas, source data, tests, and useful documentation.
