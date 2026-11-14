# BizNexa

BizNexa is a retail and wholesale analytics app. It combines a React + Vite frontend, a FastAPI backend, and PostgreSQL data access.

> Demo only: auth, tenant isolation, and production governance are not implemented. Do not use with real production data.

## Run locally

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, npm, and PostgreSQL.

1. Copy `.env.example` to `.env` and set `DATABASE_URL`.
2. Start the backend:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:PYTHONPATH = "$PWD\backend"
.\.venv\Scripts\python.exe -m uvicorn biznexa.main:app --reload --host 127.0.0.1 --port 8000
```

3. In a second terminal, start the frontend:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

4. Open the local Vite URL shown in the terminal.

Checks:
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Deploy

See the [Render + Vercel deployment guide](./docs/deployment-render-vercel.md) for setup steps. The optional [render.yaml](./render.yaml) configures the Render API service.

## Validate

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend
npm --prefix frontend run build
```

## Docs

- [Architecture](./docs/architecture.md)
- [KPI dictionary](./docs/kpi-dictionary.md)
- [Synthetic dataset](./docs/synthetic-dataset.md)
- [Deployment guide](./docs/deployment-render-vercel.md)
