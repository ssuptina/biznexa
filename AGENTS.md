# BizNexa contributor guide

## Stack

- Frontend: React 19 + TypeScript + Vite
- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Data: Supabase/PostgreSQL analytics schema

## Project rules

- Keep the existing frontend/backend split.
- Store real `DATABASE_URL` only in local root `.env` or `backend/.env`.
- Never expose secrets in React or public env files.
- Use the backend for analytics and database access.
- Keep synthetic data clearly marked as demo-only.

## Local run

```powershell
npm --prefix frontend install
npm --prefix frontend run dev

.venv\Scripts\python.exe -m pip install -e .
$env:PYTHONPATH = 'D:\Project\BizNexa\backend'
.venv\Scripts\python.exe -m uvicorn biznexa.main:app --host 127.0.0.1 --port 8000
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend
```

## Important

- Use parameterized SQL and input validation.
- Do not silently fake data when an API call fails.
- Preserve migrations, schema definitions, tests, and documentation.
