# Deploy BizNexa with a Render API and Vercel frontend

This guide deploys the FastAPI backend to Render and the React/Vite frontend to Vercel. The frontend and backend are separate services:

```text
Browser → Vercel frontend → Render API → Supabase PostgreSQL
```

The browser must never receive the database URL. `DATABASE_URL` belongs only in Render. `VITE_API_BASE_URL` is public and points to the Render API.

> **Before deploying:** BizNexa does not yet implement authentication, tenant isolation, or production data governance. Do not expose sensitive or private business data through this app.

## What stays in the repository

- Keep the `frontend/` application and its `package.json`.
- Keep the FastAPI code under `backend/`, the root `pyproject.toml`, and the root `render.yaml`.
- Keep `frontend/vite.config.ts`; its proxy is for local development and does not direct production traffic.
- Keep your root `.env` local and untracked. Do not copy its database URL into Vercel or a `VITE_*` setting.
- The old Vercel backend adapter is not used. Vercel will build only the `frontend/` directory.

## 1. Deploy the API on Render Free

You do not need a Blueprint. To avoid the Blueprint flow shown in Render, create a single web service manually and choose the **Free** compute plan. The Blueprint itself is not a paid compute service, but a Blueprint can create services whose selected plans cost money; this repository's `render.yaml` explicitly sets `plan: free` as an additional safeguard if you choose to use it.

### Create a free web service (recommended)

1. Push the app code to the GitHub branch you want to deploy.
2. In Render, choose **New** → **Web Service** (not **Blueprint**).
3. Connect the GitHub repository and select the branch.
4. Configure the service:
   - **Name:** `biznexa-api` (or any available name).
   - **Language/Runtime:** Python 3.
   - **Branch:** the branch containing your code.
   - **Root Directory:** leave blank / repository root. Do not use `backend` or `frontend`.
   - **Build Command:** `pip install .`
   - **Start Command:** `uvicorn biznexa.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type / Compute:** select **Free**. Check the selected plan and estimated cost before creating the service; do not select Starter or another paid plan.
5. Create the Web Service. Once created, open its **Environment** page and add the variables in the next section.

If Render asks for a payment method or the selected plan shows a charge, stop before confirming. Recheck that you chose a Web Service with the **Free** compute plan, not a paid plan or another resource.

### Set Render environment variables

Open the `biznexa-api` service and go to **Environment**. Set the following values:

| Key | Value |
|---|---|
| `DATABASE_URL` | The PostgreSQL URL from Supabase **Connect**. Use the Session Pooler URL where available. URL-encode special characters in the password. |
| `FRONTEND_ORIGIN` | The production Vercel URL, for example `https://your-project.vercel.app`. Use the exact origin only: no path and no trailing slash. If you do not know the Vercel URL yet, enter a temporary value to create the service, then replace it with the real URL in section 2 and redeploy the API before the final test. |
| `APP_ENV` | `production` |
| `ANALYTICS_SCHEMA` | `public` if the analytics tables are in the `public` schema; otherwise the actual schema name. |
| `SYNTHETIC_LOAD_ENABLED` | `false` |

`DATABASE_URL` must only be set in Render. Never add it to Vercel, frontend `.env` files, source code, or a variable whose name starts with `VITE_`.

Save the variables and deploy/redeploy. Wait for the deployment to finish, then copy the public service URL from Render, for example `https://biznexa-api.onrender.com`.

### Free plan limitations and costs

Render's Free web service has no compute fee, but it is intended for hobby/testing and has important limitations:

- It spins down after 15 minutes without inbound traffic. The first request afterward can take about a minute while the service starts.
- Free instance hours are limited to 750 hours per workspace per calendar month and shared across its Free services. If exhausted, Free services are suspended until the next month.
- Its filesystem is ephemeral; do not store uploaded files or a local database there. BizNexa uses Supabase for PostgreSQL.
- Bandwidth and build pipeline usage have included limits. Monitor these on Render's **Billing** page. According to Render's current [Free instance documentation](https://render.com/docs/free), exceeding limits can suspend services or builds if no payment method is attached; with a payment method, billable overages may be charged. Other paid resources in your workspace can also cost money.
- Render may suspend a Free service that initiates unusually high outbound traffic. The API makes outbound database connections to Supabase, so keep usage moderate and monitor the service.
- Free services are not recommended for production or sensitive business data.

Do not create a Render Postgres database for this setup; the app is configured to connect to your existing Supabase PostgreSQL database.
For official details, see Render's [Free instance documentation](https://render.com/docs/free) and [Blueprint plan field](https://render.com/docs/blueprint-spec#plan).

### Verify the API and database

Open these URLs, replacing the host with your Render URL:

1. `https://<render-service>.onrender.com/health`
   - The JSON should report `"status": "ok"` and `"analytics_schema_initialized": true`.
   - Render's HTTP health check only confirms that `/health` returned a successful HTTP response. Inspect the JSON too; a degraded API can still return HTTP 200.
2. `https://<render-service>.onrender.com/health/db`
   - It should succeed and report the schema readiness information.
3. `https://<render-service>.onrender.com/docs`
   - FastAPI's interactive API documentation should load.

If the database health check reports missing tables or columns, the database is reachable but is not loaded with the schema BizNexa expects. Check the [database schema and data guide](./synthetic-dataset.md) and make sure `ANALYTICS_SCHEMA` points to the schema containing those tables. Do not run the synthetic loader against production data.

If the API cannot connect, recheck the Supabase host, URL-encoded password, and connection URL. If Supabase Network Restrictions are enabled, ensure Render's outbound connections are allowed. Review the Render service logs for startup errors; do not paste secrets into support requests or logs.

## 2. Configure or create the Vercel frontend

You can keep your existing Vercel project if it currently builds the frontend. Change its settings rather than creating a second project.

If you previously created a separate Vercel project for the **backend**, stop using that project for API hosting. Do not delete it until the Render API and Vercel frontend have passed the final checks below. Afterward, you can disable its automatic deployments or delete that backend-only Vercel project. Keep the Vercel frontend project.

1. In Vercel, open the frontend project and go to **Settings** → **Build and Development Settings**.
2. Set **Root Directory** to `frontend`.
3. Confirm the build settings:
   - Framework preset: **Vite**
   - Build command: `npm run build`
   - Output directory: `dist`
   - Install command: `npm install` (or Vercel's automatic default)
   - Leave commands at their defaults unless the project has an explicit override that conflicts with these values.
4. Go to **Settings** → **Environment Variables** and add:
   - Name: `VITE_API_BASE_URL`
   - Value: the Render service URL, e.g. `https://biznexa-api.onrender.com`, with no trailing slash.
   - Select **Production**. Also select **Preview** only if you intend preview deployments to call this same API and have configured CORS for the preview site's origin.
5. Save the settings and trigger a new deployment. Vite embeds `VITE_API_BASE_URL` into the frontend at build time, so changing it does not affect an already-built deployment.
6. Open the production Vercel URL and exercise the analytics screens. In browser developer tools, check **Network** for requests going to the Render host and check **Console** for CORS or request errors.

If the Vercel project does not exist yet, choose **Add New** → **Project**, import the repository, set the Root Directory to `frontend`, and apply the settings above. Deploy the frontend after setting `VITE_API_BASE_URL`.

### Set the exact production origin in Render

Copy the production frontend origin from Vercel's **Domains** page (or the browser address bar). In Render, set `FRONTEND_ORIGIN` to exactly that origin, such as `https://your-project.vercel.app`, then save and redeploy the API. Do not include a route, query string, or trailing slash.

The API currently permits one exact frontend origin. If you use a custom domain, use that domain as `FRONTEND_ORIGIN`. Preview URLs on other origins will be blocked by CORS unless you change the API's CORS configuration; do not use a permissive wildcard as a shortcut.

## 3. Final end-to-end check

1. Render deployment is live.
2. Render `/health` reports `status: ok` and an initialized analytics schema.
3. Render `/docs` loads.
4. Vercel's production build has `VITE_API_BASE_URL` set to the Render URL.
5. Render's `FRONTEND_ORIGIN` is set to the exact Vercel production origin and the API has been redeployed after that value was saved.
6. The deployed frontend loads analytics data without CORS errors in the browser console.

The API has no homepage route, so opening the Render root URL (`/`) may return 404. Use `/health` or `/docs` to check the service.

## Later code or setting changes

- A commit to the connected branch normally triggers deployments in both projects. If auto-deploy is disabled, deploy each service manually.
- Changes to `VITE_API_BASE_URL` require a new Vercel build/deployment.
- Changes to Render environment variables require saving/redeploying the Render service.
- Keep `DATABASE_URL` and any other server-side secrets exclusively in Render's environment settings.
- To update the frontend's production domain, update `FRONTEND_ORIGIN` in Render to the new exact origin and redeploy the API.
