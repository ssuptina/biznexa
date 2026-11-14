# BizNexa master reverse-engineering guide

This file is for personal understanding only. It is not part of the public-facing project documentation.

This is the single master file for understanding how BizNexa works end-to-end.

## 1. Project summary

BizNexa is a business analytics web app built for retail and wholesale reporting. It has:

- a React + TypeScript frontend
- a FastAPI backend
- PostgreSQL data access via SQLAlchemy and psycopg
- a Supabase/PostgreSQL analytics schema as the data source

The product is designed around one core idea: the frontend renders dashboards, but the backend performs the actual analytics and data validation.

## 2. High-level architecture

The system is split into three main layers:

1. Frontend layer
   - React app with dashboard shell
   - filters, menu, KPI cards, charts, and tables
   - UX logic and user interactions

2. API layer
   - FastAPI routes
   - request validation
   - database health checks
   - analytics endpoint contract

3. Data layer
   - PostgreSQL analytics schema
   - SQLAlchemy queries
   - business aggregates and metric logic

The flow is:

User -> Frontend -> API -> PostgreSQL analytics -> JSON response -> Frontend display

## 3. Actual code structure

Main files:

- `frontend/src/App.tsx` – app shell and page routing
- `frontend/src/services/api.ts` – shared API request helper
- `frontend/src/components/BusinessPulse.tsx` – decision signals and business pulse
- `frontend/src/components/CustomerAnalyticsDashboard.tsx` – customer analytics module
- `frontend/src/components/AnalyticsCharts.tsx` – Recharts UI panels
- `frontend/src/styles.css` – all style rules
- `backend/biznexa/main.py` – FastAPI app and routes
- `backend/biznexa/analytics.py` – overview and analytics queries
- `backend/biznexa/customer_analytics.py` – customer-specific logic
- `backend/biznexa/decision_intelligence.py` – scenario and pulse logic
- `backend/biznexa/db.py` – DB connection and health helpers
- `backend/biznexa/config.py` – environment settings

## 4. Frontend reverse engineering

### 4.1 App shell

The main shell lives in `frontend/src/App.tsx`.

This file controls:

- left sidebar navigation
- selected section
- current domain tab
- reporting period state
- API fetch lifecycle
- rendering of overview and domain-specific pages

The app does not store database logic inside React components. It mostly requests data and renders it.

### 4.2 Navigation pattern

The app defines navigation items like:

- Executive Overview
- Customer Intelligence
- Sales & Revenue
- Financial Performance
- Inventory & Supply Chain
- Decision Center

When the user clicks one, the code updates state and renders a different domain area.

### 4.3 Reporting date filters

The app accepts:

- start date
- end date
- granularity
- comparison type

This data is managed via reporting filter components and sent to the backend in API calls.

### 4.4 Data fetch helper

`frontend/src/services/api.ts` is the central helper.

It does four important things:

- builds the backend URL from `VITE_API_BASE_URL`
- sends GET and POST requests
- converts HTTP errors into a custom `ApiRequestError`
- deduplicates GET requests while they are in flight

This is a key pattern because it prevents duplicate data requests while filters are changing.

### 4.5 How the overview is displayed

The overview page renders:

- KPI cards
- revenue chart
- profit chart
- category mix
- highlights
- product grids or action tables

These all depend on data returned by the backend, not client-side computed business metrics.

### 4.6 Customer analytics UI

The customer analytics dashboard is the most complex frontend module. It includes:

- filters for customer segment, activity, and timing
- RFM grouping
- search fields
- customer table with pagination
- detail panel

The detail panel appears when a user clicks a customer row. It requests customer-specific data from a dedicated API endpoint.

### 4.7 Decision Center UI

The decision center includes:

- Business Pulse
- What-if Simulator
- Decision Impact Tracker

These are not fully automated predictions. They are evidence-based review tools that show a current metric, the calc method, and business assumptions.

### 4.8 Styling approach

All visual design lives in `frontend/src/styles.css`.

It defines:

- layout structure
- panel cards
- chart containers
- KPI card sizes
- table styles
- responsive breakpoints
- Graphite & Copper look

This entire UI is a custom dashboard style, not a generic default framework.

## 5. Backend reverse engineering

### 5.1 FastAPI entrypoint

The backend server is in `backend/biznexa/main.py`.

It creates the FastAPI app and registers routes like:

- `/health`
- `/health/db`
- `/api/analytics/synthetic/overview`
- `/api/analytics/synthetic/sales`
- `/api/analytics/synthetic/customers`
- `/api/analytics/synthetic/finance`
- `/api/analytics/synthetic/inventory`
- `/api/analytics/synthetic/suppliers`
- `/api/analytics/synthetic/decisions`
- `/api/analytics/synthetic/business-pulse`
- `/api/analytics/synthetic/scenario`

### 5.2 Validation layer

The backend validates request data before running analytics.

Examples:

- dates must be valid ISO dates
- percentages must be in legal ranges
- titles and decision outcomes cannot be blank
- query parameters are constrained to allowed values

This prevents incomplete or invalid data from entering queries.

### 5.3 Health checks

The app checks the actual database before claiming the system is healthy.

The health route verifies:

- the database can answer a real query
- the expected tables exist
- the required columns exist
- the analytics schema is configured correctly

This matters because the app is analytics-driven and should not run with a broken or mismatched schema.

### 5.4 Analytics route structure

Every analytics endpoint goes through a common wrapper called `_run_analytics`.

This wrapper catches:

- validation errors
- database/runtime errors
- SQLAlchemy errors

It converts them into clean HTTP responses.

### 5.5 SQL and business logic modules

The main analytics logic lives in files such as:

- `backend/biznexa/analytics.py`
- `backend/biznexa/customer_analytics.py`
- `backend/biznexa/decision_intelligence.py`

These modules build queries against Postgres tables like:

- `customers`
- `sales_orders`
- `sales_order_lines`
- `returns`
- `products`
- `inventory_snapshots`
- `suppliers`
- `purchase_orders`
- `goods_receipts`
- `monthly_budgets`

The SQL is intended to answer business questions like:

- what is gross sales for the selected period?
- what is gross profit?
- how do categories contribute to sales?
- which customers are active or inactive?
- which products are low stock?
- what is the current risk or recommendation signal?

## 6. Database and schema rules

The app expects a known analytics contract.

If the configured schema does not have the required tables and columns, the backend raises an error instead of continuing with broken data.

This is a strong design decision because it avoids misleading analytics output.

## 7. How the overall flow works

Here is the exact request lifecycle:

1. User selects a period or filter in the frontend
2. The front-end sends a request to the API
3. FastAPI validates the request
4. The backend reads the selected analytics schema
5. PostgreSQL executes SQL aggregation queries
6. The backend converts rows to JSON
7. The frontend receives the response
8. React renders the KPI cards, charts, tables, and signals

This is the main reverse-engineering pattern of the app.

## 8. Why the app is split this way

This app separates responsibilities very clearly:

- Frontend = what users see
- Backend = how the data is validated and computed
- Database = where the metrics are calculated and stored

This separation makes the application easier to maintain and safer to extend.

## 9. Decision intelligence logic

The app includes decision support logic, but it does not present it as factory-perfect prediction.

The product explicitly separates:

- descriptive analytics
- scenario modeling
- recommendation signals
- a human review decision

This is important because the project is analytical, not autonomous.

## 10. What the app is not

The project is not yet a full production system in the following areas:

- authentication
- tenant isolation
- production governance
- validated enterprise-grade data controls

So the architecture is sound as a demo and analytics prototype, but it still needs business approval and security controls before live production use.

## 11. The big picture

BizNexa is a layered analytics system built to show business insight clearly.

It works like this:

- the browser captures a user decision
- the API acts as a controlled gateway
- PostgreSQL does the heavy analytical work
- the frontend displays results in readable business terms

The design is intentionally simple, readable, and modular.

## 12. Full end-to-end summary

If you want the shortest possible explanation:

BizNexa is a dashboard app where the React UI handles display and interaction, the FastAPI backend handles validation and analytics logic, and PostgreSQL provides the reporting and metric engine. The app is designed to be clear, layered, and understandable, with the most important business decisions kept in the backend rather than the browser.

## 13. Recommended reading order

If you want to reverse-engineer the project in the easiest path, read in this order:

1. `frontend/src/App.tsx`
2. `frontend/src/services/api.ts`
3. `backend/biznexa/main.py`
4. `backend/biznexa/analytics.py`
5. `backend/biznexa/customer_analytics.py`
6. `frontend/src/components/BusinessPulse.tsx`
7. `frontend/src/styles.css`

That flow will give you the best mental model of the actual system.
