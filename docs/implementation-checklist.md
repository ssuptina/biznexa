# BizNexa Implementation Checklist

## Project foundation

- [x] Inspect the initial workspace and preserve the existing backend foundation.
- [x] Capture the initial business and architecture brief in the project conversation.
- [x] Create backend configuration, FastAPI health endpoint, SQLAlchemy sales models, and first Alembic migration.
- [x] Create the React + TypeScript frontend and responsive application shell.
- [x] Build the illustrative executive overview with period selection, charts, insight details, and a filterable/sortable action table.
- [x] Remove frontend demo KPI data and use the validated synthetic analytics endpoint for the overview.
- [x] Document current architecture, KPI definitions, and implementation status.
- [x] Inspect and profile the supplied synthetic dataset and document its loading plan.
- [x] Add a schema-aware analytics API and explicit database health checks for Supabase.
- [x] Run the frontend production build and inspect the page in the integrated browser.
- [x] Centralize frontend API requests and add an optional non-secret Vite API base URL.
- [x] Add root contributor guidance for the actual frontend, backend, Supabase, and validation workflow.
- [x] Remove generated frontend build output and local test/lint caches after checking references.

## Phase 1 — Requirements and blueprint

- [x] Draft the requirements and architecture blueprint (captured in the project conversation).
- [ ] Confirm pilot workflow, stakeholders, and success criteria with the business owner.
- [ ] Confirm organization / tenant scope, currency, fiscal calendar, time zone, privacy jurisdiction, and access rules.

## Phase 2 — KPI and data governance

- [x] Create an initial KPI dictionary for metrics shown in the executive overview.
- [ ] Approve revenue, discounts, returns, COGS, churn/inactivity, inventory health, and supplier delivery definitions.
- [ ] Inventory source systems and map fields to canonical entities and analytical facts.
- [ ] Approve dimensional model, fact grains, snapshot rules, and history behavior.

## Phase 3 — Data foundation

- [x] Define initial customer, product, sales order, and sales line models and migration.
- [ ] Configure PostgreSQL locally and verify upgrade / downgrade behavior.
- [ ] Validate the manually imported Supabase schema and relationships after database connectivity is restored.
- [ ] Load and query the synthetic data in a configured local PostgreSQL development database.
- [ ] Extend the schema for returns, inventory, suppliers, receipts, budgets, source batches, and audit needs as approved.
- [ ] Build a reproducible synthetic dataset with declared assumptions and data-quality edge cases.
- [ ] Add automated integrity and KPI calculation tests.

## Phase 4 — ETL/ELT and analytical models

- [ ] Build idempotent landing, validation, reconciliation, and dimensional loads.
- [ ] Add source lineage, batch status, quality results, and rejected-row handling.
- [ ] Implement analytical facts and dimensions with documented grain and additive behavior.

## Phase 5 — Power BI semantic model

- [ ] Define reusable measures, date roles, security roles, and report specifications.
- [ ] Reconcile semantic measures to approved SQL test cases.

## Phase 6 — Intelligence modules

- [x] Build the Graphite & Copper executive overview UI.
- [x] Implement customer, sales, finance, inventory, supplier, and decision analytics against validated synthetic APIs.
- [x] Connect the executive overview and navigation modules to synthetic API responses; production governance remains pending.
- [x] Add shared date presets, custom ranges, aggregation granularity, period comparisons, and contextual module filters.
- [x] Add API-calculated performance highlights and a selectable daily sales heatmap with explicit empty-range behavior.

## Phase 7 — Predictive and prescriptive analytics

- [ ] Establish simple forecast / churn baselines and appropriate time-based holdouts.
- [ ] Evaluate model performance, leakage, calibration, and uncertainty before showing model-based signals as validated.

## Phase 8 — Decision workflow and governance

- [ ] Implement authorization, approval transitions, action ownership, and audit history.
- [ ] Track estimated benefit separately from realized outcomes; require approval for consequential actions.

## Phase 9 — Production readiness

- [ ] Add API, data-integrity, calculation, integration, authorization, and accessibility tests.
- [ ] Validate performance, security, backups, and recovery requirements.
- [ ] Select deployment and Power BI licensing after requirements are confirmed.

## Current verification

- Frontend `npm --prefix frontend run build`: passed after period filtering, heatmap, and responsive-layout changes.
- Backend `pytest -q backend/tests`: 10 passed, 2 skipped because the optional local CSV source package is absent.
- Ruff checks for the backend package: passed.
- Supabase `/health/db`: ready; the configured analytics schema passed its table-and-column contract check.
- Live Supabase checks passed for all overview granularities previously tested, daily zero-filled sales, empty out-of-range dates, weekly sales, as-of inventory snapshots, supplier date filters, and decision context filters.
- Integrated-browser checks confirmed the date filter updates the overview and heatmap, reset restores all available data, the supplied nectar image loads, and the 390px mobile viewport has no horizontal page overflow.
- Health endpoint tests use the async HTTP client; no Starlette test-client deprecation warning is emitted.
- No local CSV package is required for Supabase runtime access.
- Git status: unavailable because this workspace is not currently a Git repository.
