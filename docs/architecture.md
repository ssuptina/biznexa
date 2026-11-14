# Architecture

BizNexa is a retail analytics app with a Vite React frontend and a FastAPI backend. The backend reads analytics from PostgreSQL, mainly from a Supabase schema.

## Layers

- Frontend: dashboard shell, KPI cards, charts, filters, and analytics views.
- Backend: API routes, validation, SQLAlchemy access, and analytics logic.
- Database: PostgreSQL schema with orders, customers, products, returns, inventory, and supplier data.

## Current state

- The app is read-only for analytics.
- Health checks verify connectivity and schema readiness.
- Synthetic demo data is separate from production data.
- Auth, tenant isolation, and full production governance are still pending.

## Key files

- `frontend/src/App.tsx`
- `frontend/src/services/api.ts`
- `backend/biznexa/main.py`
- `backend/biznexa/analytics.py`
- `backend/biznexa/customer_analytics.py`
