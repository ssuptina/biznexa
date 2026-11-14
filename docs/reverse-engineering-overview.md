# BizNexa reverse-engineering overview

This file explains how the website was built, how the pieces connect, and what each layer is doing from a software-engineering point of view.

## 1. What the project is

BizNexa is a business analytics dashboard for retail and wholesale data. It has:

- a React + TypeScript frontend in `frontend/`
- a FastAPI backend in `backend/`
- PostgreSQL data access with SQLAlchemy and psycopg
- a Supabase/PostgreSQL analytics schema as the live data source

The product is designed around one idea: the UI shows KPI cards, charts, and decision signals, but the actual logic and data aggregation happen in the backend.

## 2. The real architecture

The project is not built as a single app. It is split into layers:

1. Frontend layer
   - Renders the dashboard shell
   - Uses filters and navigation
   - Calls backend API endpoints
   - Displays charts, cards, and action tables

2. API layer
   - Built with FastAPI
   - Validates inputs
   - Protects access to analytics queries
   - Runs SQL against PostgreSQL

3. Analytics layer
   - Contains business logic for overview, sales, customer, inventory, finance, supplier, and decision data
   - Uses SQL and PostgreSQL aggregates instead of browser-side calculation

4. Database layer
   - Reads from the configured schema
   - Validates the schema contract before using the data
   - Health checks confirm that tables and columns exist

## 3. Why the app is structured this way

This is a classic layered architecture:

- the browser should not know database details
- the front-end should not calculate complicated business KPIs
- the backend owns validation, filtering, and reporting logic
- Postgres becomes the actual processor for aggregated analytics

That is why the frontend mostly asks for data and renders it.

## 4. Frontend entry points

Key files:

- `frontend/src/App.tsx` – main shell, nav, period filter, page state
- `frontend/src/services/api.ts` – shared HTTP helper for GET/POST calls
- `frontend/src/components/BusinessPulse.tsx` – evidence cards and business pulse UI
- `frontend/src/components/CustomerAnalyticsDashboard.tsx` – customer analytics dashboard
- `frontend/src/components/AnalyticsCharts.tsx` – chart components

The app loads a navigation shell and then swaps sections such as:

- Executive Overview
- Customer Intelligence
- Sales & Revenue
- Financial Performance
- Inventory & Supply Chain
- Decision Center

## 5. How the frontend works

The flow is:

1. User chooses a reporting period and comparison mode
2. App updates state
3. App calls the relevant API route
4. Response is stored in local React state
5. Components render KPI cards, tables, and charts

The frontend is intentionally thin. Most serious logic lives in the backend.

## 6. API service pattern

The shared request helper in `frontend/src/services/api.ts` does three important things:

- builds the full URL from `VITE_API_BASE_URL`
- sends JSON requests
- throws a custom `ApiRequestError` when the server responds with an error

It also prevents duplicate in-flight GET requests using a map called `inFlightGetRequests`.

This is important because the UI may request the same dataset multiple times while filters or tabs are changing.

## 7. How the backend is started

The backend is a FastAPI app created in `backend/biznexa/main.py`.

It includes:

- CORS configuration
- health endpoints
- analytics endpoints for synthetic data
- scenario and decision endpoints

The app loads settings from config and checks the database before serving some routes.

## 8. Health and readiness checks

The app does not assume the database works just because the process started.

It exposes:

- `/health`
- `/health/db`

These endpoints perform real checks.

The backend verifies:

- the database responds
- the expected analytics tables exist
- required columns are present
- the configuration points to the right schema

This keeps the app honest and avoids fake or stale data.

## 9. Analytics route structure

The backend has read-only analytics endpoints such as:

- `/api/analytics/synthetic/overview`
- `/api/analytics/synthetic/sales`
- `/api/analytics/synthetic/customers`
- `/api/analytics/synthetic/finance`
- `/api/analytics/synthetic/inventory`
- `/api/analytics/synthetic/suppliers`
- `/api/analytics/synthetic/decisions`
- `/api/analytics/synthetic/business-pulse`

These are grouped under the same API contract and are designed to return JSON for the UI.

## 10. The real processing engine

The business logic is mostly in:

- `backend/biznexa/analytics.py`
- `backend/biznexa/customer_analytics.py`
- `backend/biznexa/decision_intelligence.py`

These modules use SQL queries over PostgreSQL tables like:

- `sales_orders`
- `sales_order_lines`
- `customers`
- `products`
- `returns`
- `inventory_snapshots`
- `suppliers`
- `purchase_orders`
- `monthly_budgets`

The logic is not done in the frontend. It is done in SQL, then returned as JSON.

## 11. Why SQL is used heavily

The analytics layer wants to answer questions like:

- total gross sales in a period
- customer activity in a date range
- product category mix
- low stock conditions
- profit and margin by time period

These are all aggregate operations best handled by PostgreSQL. It is faster, more reliable, and much easier to reason about for reporting.

## 12. Data contract and schema safety

The project validates schema readiness. That is one of the most important ideas in this app.

It checks for expected tables and columns before saying the analytics system is working.

This is important because otherwise the UI could render broken or misleading numbers.

## 13. Business pulse and decision support

The app includes features that do not pretend to be fully autonomous intelligence.

Examples:

- Business Pulse shows evidence-driven signals
- What-if Simulator runs scenarios from assumptions
- Decision Impact Tracker stores recorded decisions and outcomes

The interface clearly states these are review aids and not guaranteed predictions.

## 14. How state flows in the app

The app state is driven by a few main values:

- active section
- reporting period
- comparison mode
- granularity
- selected domain tab
- API response data

When filters change, the app requests new data and re-renders chart panels.

That is the core pattern behind the dashboard.

## 15. Why this matters for reverse engineering

If you want to understand the project, think of it like this:

- navigation and views = frontend UI
- API routes = backend contract
- SQL queries = business logic
- configured schema = underlying data layer
- chart cards = presentation of analytics results

Once you understand this split, the whole project becomes much easier to trace.

## 16. Final summary

BizNexa is a structured analytics app with a simple but effective pattern:

- frontend gathers user intent
- backend validates and calculates
- PostgreSQL handles analytics
- UI renders the final result

The project is a strong example of how to separate reporting, interface, and business logic cleanly.
