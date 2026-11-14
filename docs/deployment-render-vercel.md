# Deploy on Render + Vercel

## Simple setup

- API: Render web service
- Frontend: Vercel app
- Database: Supabase PostgreSQL

## Required env vars

- Render: `DATABASE_URL`, `FRONTEND_ORIGIN`, `APP_ENV`, `ANALYTICS_SCHEMA`
- Vercel: `VITE_API_BASE_URL`

## Recommended flow

1. Push the repo.
2. Create a Render Python web service.
3. Set the backend env vars and deploy.
4. Create or update the Vercel frontend with `frontend` as the root directory.
5. Point `VITE_API_BASE_URL` to the Render API URL.

## Check

- `https://<render>/health`
- `https://<render>/health/db`
- `https://<render>/docs`

Keep `DATABASE_URL` server-side only. Do not put it in frontend env or source code.
