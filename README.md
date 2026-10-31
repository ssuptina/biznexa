# BizNexa

Business intelligence for retail, wholesale, and distribution. The app uses a React/TypeScript frontend, a FastAPI backend, and PostgreSQL (including Supabase PostgreSQL).

> This is an actively developed application, not a production-ready analytics platform. Authentication, tenant isolation, and production data governance are not implemented.

## Stack

- Frontend: React 19, TypeScript, Vite, Recharts
- Backend: Python 3.11+, FastAPI, SQLAlchemy, psycopg
- Database: PostgreSQL; Alembic migrations

## Run locally

Prerequisites: Python 3.11+, Node.js 20.19+ (or 22.12+), npm, and PostgreSQL.

Configure `.env` from `.env.example` with the server-side `DATABASE_URL` and `ANALYTICS_SCHEMA`. Never put database credentials in frontend `VITE_*` variables.

From the project root, start the backend:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:PYTHONPATH = 'D:\Project\BizNexa\backend'
.\.venv\Scripts\python.exe -m uvicorn biznexa.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

## API and verification

- Health: `GET /health` and `GET /health/db`
- Analytics: `/api/analytics/synthetic/` — overview, sales, customers, finance, inventory, suppliers, and decisions
- Interactive API docs: `http://127.0.0.1:8000/docs`

```powershell
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend
```

Analytics read the configured PostgreSQL schema. Startup does not import or reset data. The optional synthetic loader is development-only; never run it against production data.

## Documentation

- [Architecture](./docs/architecture.md)
- [Data flow diagram](./docs/data-flow.md)
- [Theoretical foundation](./docs/theoretical-foundation.md)
- [KPI dictionary](./docs/kpi-dictionary.md)
- [Database source and table contract](./docs/synthetic-dataset.md)
- [Implementation checklist](./docs/implementation-checklist.md)
- [Repository audit](./docs/repository-audit.md)
