# BizNexa Architecture

## Current build state

BizNexa is a modular application for retail, wholesale, and distribution analytics. The React + TypeScript frontend and FastAPI backend can read analytics data from a configured PostgreSQL schema, including Supabase-hosted PostgreSQL. SQLAlchemy and Alembic provide a PostgreSQL persistence foundation. Production ingestion, authorization, tenant isolation, and approved production KPI policies remain future work.

For a standalone visual of the implemented runtime path and the optional/planned data processes, see the [Data Flow Diagram](./data-flow.md).

The frontend reads validated aggregates from the configured API schema. For Supabase, `ANALYTICS_SCHEMA` defaults to `public`; set it to the schema containing the imported analytics tables. The CSV source is optional and loaded only by an explicit development-only loader into `biznexa_synthetic`; it does not populate or overwrite existing operational tables. Database health is reported only after a real `SELECT 1` and schema check succeed.

## Frontend

- Vite serves the React application in development; TypeScript type-checks the build.
- A shared graphite navigation shell frames the executive overview. Each analytics navigation item calls a corresponding API route and renders live, loading, empty, or error states.
- The executive overview consumes validated synthetic analytics from the API. Presentation components do not define KPI calculations. Requests are centralized in `frontend/src/services/api.ts`, with no database credentials in the browser.
- Recharts renders the responsive revenue/profit combo chart and category composition. Chart code loads as a separate chunk so it does not block the application shell.
- The overview displays the source period, KPI totals, monthly trend, and category mix returned by the API.
- Decision actions are threshold-based and explicitly labeled as such. Predictive analytics does not claim a trained model; customer inactivity is exposed as a configurable business rule.
- The Vite development server proxies API requests to `http://127.0.0.1:8000`.

## Backend and data

- FastAPI exposes `/health`, `/health/db`, and read-only analytics routes under `/api/analytics/synthetic/`. `/health/db` executes `SELECT 1`; analytics return HTTP 503 with an actionable error when the database or isolated schema is unavailable.
- SQLAlchemy models and the first Alembic migration define customers, products, sales orders, and sales order lines.
- Source-system IDs are namespaced by source system to support future ingestion and traceability.
- Monetary values use fixed-precision numeric columns; line-level unit price, discount, and unit cost are stored for historical reproducibility.
- Production authorization, tenant isolation, customer privacy controls, and a dimensional warehouse remain future production work. The current synthetic analytics API implements return handling, inventory snapshot rules, budgets, supplier receipt timing, and KPI calculations over the supplied data.
- Supabase is the runtime source of truth. The backend does not import CSV files at startup; it reads the configured `ANALYTICS_SCHEMA` and does not update or delete imported rows.

## Decisions and pending confirmation

| Area | Current choice | Status / revisit |
|---|---|---|
| Application design | Modular frontend and backend, no microservices | Keep until scale or isolation requirements justify a split |
| Database | PostgreSQL, operational foundation first | Configure a local instance and validate migrations before loading data |
| Analytics | API-backed synthetic aggregates with explicit metric policy | Add governed facts, models, and approved KPI contracts before production data |
| Reporting | Reusable analytical UI; Power BI remains planned | Define semantic model after source and KPI governance |
| Predictive insights | Clearly labeled illustrative scenarios | Do not call predictions validated until evaluated against a suitable holdout and baseline |
| Identity and privacy | Not selected | Confirm identity provider, company scope, row-level access, data minimization, and retention |

## Next architecture milestone

Approve the first pilot's source systems and accounting rules, then implement production access controls and a production ingestion boundary. The frontend consumes the validated synthetic KPI endpoints; production KPIs still require governed contracts.
