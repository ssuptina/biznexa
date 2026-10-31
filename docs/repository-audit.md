# BizNexa Repository Audit — Phase 1

**Scope:** Read-only source, configuration, migration, test, and documentation review. No database was queried or changed, no backend server was started, and no credentials were read or included. Findings about live Supabase data, roles, grants, RLS, and runtime performance remain unverified.

## 1. Existing architecture

- **Frontend:** React 19, TypeScript, and Vite. `frontend/src/main.tsx` mounts the application; `App.tsx` owns navigation, the executive overview, and domain routing. Customer Intelligence is lazy-loaded from `CustomerAnalyticsDashboard.tsx`; reusable charts are in `AnalyticsCharts.tsx`; reporting-period controls and branding are in their own components. `services/api.ts` centralizes GET requests and coalesces identical in-flight requests.
- **Backend:** FastAPI routes are in `backend/biznexa/main.py`. PostgreSQL analytics and calculations are implemented in `analytics.py` and `customer_analytics.py`, with SQLAlchemy/psycopg connection setup in `db.py` and environment configuration in `config.py`.
- **Database:** Runtime analytics query manually imported tables in the configured PostgreSQL schema (documented as Supabase). The read paths use parameterized values and PostgreSQL aggregation. An independent SQLAlchemy model and Alembic migration define a smaller sales persistence foundation.
- **Validation and docs:** The optional `backend/scripts/seed_synthetic.py` validates CSV data and can explicitly load it into `biznexa_synthetic`. That CSV package is absent in this workspace. Architecture, dataset, KPI, and implementation status are documented under `docs/`.

## 2. Implemented surfaces and current capabilities

- The executive overview uses backend aggregates, a shared reporting-period filter, and Recharts.
- Customer Intelligence has backend filtering and pagination, cohort retention, RFM classifications, customer detail, and a searchable customer table. The dashboard has chart sections and loading/error states.
- Sales, finance, inventory, suppliers, and decisions have read-only API endpoints. The current domain tabs display existing API aggregates; transaction-level detail is not exposed.
- Health endpoints perform real connectivity/schema checks. The frontend does not substitute mock records on API failure.
- `BrandLogo.tsx` and `frontend/public/assets/` provide the branding assets used by the shell.
- The principal runtime files are `frontend/src/App.tsx`, `frontend/src/components/CustomerAnalyticsDashboard.tsx`, `frontend/src/components/AnalyticsCharts.tsx`, `frontend/src/components/ReportingPeriodFilter.tsx`, `frontend/src/services/api.ts`, and `backend/biznexa/{main,analytics,customer_analytics,db,config}.py`.

## 3. Duplicate or redundant implementations

- `analytics.py` and `customer_analytics.py` each implement small result-serialization helpers (`_rows`, `_one`, and decimal/date conversion). They can be consolidated when those modules are next refactored, but this is not a correctness blocker.
- The Alembic ORM model/migration and the imported analytics schema are two different persistence contracts; they are not duplicate implementations that can safely be merged without deciding which schema is authoritative.
- No source file was identified as safe to delete in this audit. `react-is` has no direct application import, but it may serve Recharts' package/peer requirements; do not remove it without checking the dependency contract.

## 4. Findings and risks

| Priority | Finding | Evidence and impact |
|---|---|---|
| High before production | Analytics and customer-detail endpoints have no authentication or authorization. | The API is directly registered in `main.py`; the README also documents the limitation. Do not expose it to untrusted users or real customer data until an access model is selected and enforced. |
| High before production | Supabase RLS, database grants, and the privilege level of `DATABASE_URL` were not verified. | The application connects directly through SQLAlchemy; there is no Supabase client integration or policy/migration in the reviewed source. RLS may not protect access made by a privileged backend role. Verification requires a safe, read-only review of the actual database roles and policies. |
| Medium | The schema name is interpolated into SQL after being read from configuration; the schema-name regex is checked by the health function, not by each analytics query. | `analytics.py` sets `SCHEMA` from settings and uses it in SQL text; `_schema_guard` only checks for the existence of a table. Validate the identifier once at settings/startup and use safe identifier composition consistently. |
| Medium | The health contract can report a schema ready while supplier analytics requires an undeclared column. | `analytics.suppliers()` filters on `purchase_orders.order_date`, but `_ANALYTICS_SCHEMA_CONTRACT` does not require that column. The route can consequently fail after a passing schema check. |
| Medium | Supplier on-time rate can be misleading. | Late lines are counted from the last receipt date, while the denominator is lines with received quantity at least the ordered quantity. These populations need a consistent completion and due-date rule; the present subtraction can produce misleading or negative rates. |
| Medium | Finance percentage variance is reported as zero when budget is zero. | `finance()` substitutes `Decimal(0)` for a percentage whose denominator is zero. A missing/zero budget should be represented as undefined, not as a valid 0% variance. |
| Medium | Database exceptions are partially returned to API clients. | `_run_analytics()` includes the first line of the SQLAlchemy exception in an HTTP 503 detail. Keep actionable client errors, but move technical details to protected server logs with redaction. |
| Medium | The ORM/migration schema does not match the runtime analytics contract. | Migration `0001_sales_foundation` creates singular `customer`, `product`, `sales_order`, and `sales_order_line` tables; analytics expects plural imported tables and many additional domains. Running the migration does not initialize the analytics schema. Applying it to a live Supabase project without a deployment plan could create an unintended parallel schema. |
| Medium | Database quality and constraints cover only part of the data architecture. | The migration adds useful FK, uniqueness, check, and numeric constraints for its four tables, but the runtime schema has no reviewed migration/DDL contract for returns, purchasing, inventory, suppliers, budgets, or other documented datasets. The CSV validator is not a substitute for live constraints or a live quality report. |
| Medium | Metric documentation has drifted from code and runtime setup. | `architecture.md` describes a pending/unconfigured database, while `synthetic-dataset.md` documents manually imported Supabase tables. The initial KPI dictionary still calls some implemented calculations unimplemented and includes stale illustrative values. |
| Medium | The optional loader cannot be used with this checkout as-is. | `backend/biznexa_data/` CSV files are absent, so the two source-data tests skip. Loader behavior should remain opt-in and should not be run against production data. |
| Medium | Interactive BI scope is incomplete. | Customer filtering/detail and reporting-period controls exist, but there is no frontend test suite or test script, and no verified export, persistent saved-view, or general chart cross-filter workflow. Several workspace destinations remain descriptive placeholders. |
| Low | Supplier and inventory recommendations are threshold heuristics, not demand forecasts. | Inventory recommends the product minimum order quantity when availability is below a fixed threshold; the decision endpoint emits threshold-based actions. Keep labels explicit and do not describe these as predictive outputs. |
| Low | The customer service is a large SQL-heavy module with repeated work. | Customer analytics materializes per-request temporary tables and reuses them, which is an improvement, but still runs multiple database statements and assembles several analytical views per request. A previous investigation measured about 5.4 seconds for a default customer query; this audit did not repeat that measurement. |

### Correctness slice completed after the audit

- Analytics requests now validate the configured schema identifier before interpolating it into SQL.
- The health contract now requires `purchase_orders.order_date`.
- Supplier date filters stay on the purchase-order join, preserving suppliers with no orders in the selected range. On-time rate and delay now include only completed lines with delivery and promise dates; a rate with no qualifying lines is unavailable.
- Percentage variance is unavailable when the budget is zero.
- Analytics SQL exceptions are logged server-side and returned as a generic 503 detail rather than raw database diagnostics.

## 5. Database and data-quality review

- The source contracts include key customer, product, order, return, inventory, supplier, purchase, receipt, and budget columns. The health check verifies required table/column presence, not primary/foreign keys, unique constraints, checks, row-level policies, duplicate data, or cross-table referential integrity.
- The optional CSV validator checks declared row counts, duplicate keys, required values, foreign references, and inventory invariants. It writes a report and requires an explicit `--load` for inserts. Its input data is not present here.
- No database schema inspection or RLS/grant verification was performed. No schema changes are recommended until the live schema, existing constraints, deployment target, and backup/rollback strategy are reviewed.

## 6. Performance and UX assessment

- Existing wins include PostgreSQL-side aggregation, a shared API client, lazy-loaded customer/chart modules, in-flight GET coalescing, chart animation reduction, and pagination for customer records.
- Backend/database, browser rendering, and initial-load timings were not measured in this audit. The prior customer query timing suggests the main next measurement is end-to-end tracing that separates SQL time, response transfer, React work, and chart rendering.
- The generic domain tabs currently reuse API payload arrays in tables rather than offering domain-specific interactive visualizations. The customer analytics dashboard is the most developed analytical workspace.
- Meaningful next performance work should be measurement-led: capture query plans and timings, inspect indexes against actual filters/joins, avoid repeating full customer aggregates unnecessarily, and profile browser rendering before adding caches or indexes.

## 7. Dependencies and tests

- Python dependencies are defined in `pyproject.toml`; frontend dependencies and the lockfile are in `frontend/package.json` and `frontend/package-lock.json`.
- The frontend has a production build script, but no test script or discovered frontend test files.
- Phase 1 backend baseline: **24 passed, 2 skipped**. After the correctness slice: **31 passed, 2 skipped**. The skipped tests require the absent optional CSV package.
- Backend lint baseline: **Ruff passed**.
- Frontend production build: passed immediately before this audit during the preceding formatting task; it was not rerun for this read-only audit.

## 8. Recommended incremental plan

1. **Close correctness and safety gaps without touching data:** validate `ANALYTICS_SCHEMA` at configuration/startup; align the health contract with supplier query requirements; correct supplier delivery-rate cohorts and zero-budget variance semantics; stop returning raw database exception text.
2. **Confirm database ownership and access:** inspect the actual schema, keys/indexes, grants, RLS, and the role used by the backend. Decide whether Alembic owns the imported schema or a separate application schema. Produce a migration/rollback proposal; do not apply schema changes or data fixes without explicit approval.
3. **Reconcile metric contracts:** establish one approved source/status/returns/currency/date policy, update the KPI dictionary and architecture docs, then add calculation tests for boundary cases and source-table reconciliation.
4. **Build a production-grade data-quality path:** report live counts, missing values, duplicates, and referential-integrity violations read-only; define correction procedures before adding constraints.
5. **Measure and optimize:** capture representative `EXPLAIN (ANALYZE, BUFFERS)` output and browser/API traces; then add only indexes or caches justified by those measurements.
6. **Expand BI interactions and tests:** add frontend test infrastructure, then implement export, chart-to-table drill-down, cross-filtering, and saved-view persistence against real filtered endpoints.
7. **Harden decision intelligence:** return period, evidence, calculation, and limitations with each threshold action; avoid estimated impacts unless their assumptions are explicit and reviewed.

## Verification limits

This phase did not start or stop the backend and did not connect to Supabase. Therefore, live data counts, database relationships and indexes, RLS, grants, API response time, and database query plans are not certified by this report.
