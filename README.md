# BizNexa

Retail and wholesale analytics app with a React/Vite frontend, FastAPI backend, and PostgreSQL database.

> **Development status:** Authentication, tenant isolation, and production data governance are not implemented. Do not use with sensitive production data.

## Run locally

Requirements: Python 3.11+, Node.js 20.19+ (or 22.12+), npm, and PostgreSQL.

1. If you do not already have a root `.env`, copy `.env.example` to `.env`.
2. Set `DATABASE_URL` in `.env`. For Supabase, open the project dashboard, select **Connect**, choose **Transaction pooler**, and copy its connection URL. Keep it out of frontend variables.
3. Install and start the backend:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
   $env:PYTHONPATH = "$PWD\backend"
   .\.venv\Scripts\python.exe -m uvicorn biznexa.main:app --reload --host 127.0.0.1 --port 8000
   ```

4. In a second terminal, install and start the frontend:

   ```powershell
   npm --prefix frontend install
   npm --prefix frontend run dev
   ```

5. Open the Vite URL shown in the terminal. The local frontend proxies API requests to the backend.

API checks: `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`.

## Deployment

For step-by-step Render backend and Vercel frontend deployment instructions, including how to select Render's Free web-service plan without using a Blueprint, see the [Render + Vercel deployment guide](./docs/deployment-render-vercel.md). The optional root [render.yaml](./render.yaml) specifies the Render API service with `plan: free`.

## Tests and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend
npm --prefix frontend run build
```

## Project documentation

- [Architecture](./docs/architecture.md)
- [Render + Vercel deployment guide](./docs/deployment-render-vercel.md)
- [KPI definitions](./docs/kpi-dictionary.md)
- [Database schema and data](./docs/synthetic-dataset.md)
