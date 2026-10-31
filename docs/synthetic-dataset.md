# Supabase data source

## Runtime source of truth

BizNexa reads manually imported PostgreSQL tables from Supabase. Local CSV files are not required by the application, backend startup, frontend, or analytics API. The backend never imports or resets data during startup.

Set the server-side environment values in the local `.env` file:

```env
DATABASE_URL=postgresql+psycopg://...
ANALYTICS_SCHEMA=BizNexa
```

Use the PostgreSQL connection string from Supabase Dashboard → Connect. Do not use the Supabase project URL, anon key, or service-role key as `DATABASE_URL`. Keep the credentials server-side.

The current local Supabase tables are in the `BizNexa` schema. Set `ANALYTICS_SCHEMA` to the schema containing your imported tables; it defaults to `public` when unset. Analytics queries use unquoted PostgreSQL identifiers, which are folded to lowercase.

## Expected table contract

The analytics API validates these tables and required columns when a health check is requested:

- `customers(customer_id, customer_name)`
- `products(product_id, product_name, category, minimum_order_qty)`
- `sales_orders(order_id, customer_id, order_date, order_status)`
- `sales_order_lines(order_id, order_line_id, product_id, quantity, line_revenue_usd, line_cogs_usd)`
- `returns(order_line_id, return_date, refund_amount_usd)`
- `inventory_snapshots(snapshot_date, warehouse_id, product_id, on_hand_qty, reserved_qty, available_qty, unit_cost_usd, inventory_value_usd)`
- `warehouses(warehouse_id, warehouse_name)`
- `suppliers(supplier_id, supplier_name, quality_rating)`
- `purchase_orders(purchase_order_id, supplier_id, promised_delivery_date)`
- `purchase_order_lines(purchase_order_line_id, purchase_order_id, quantity_ordered, line_cost_usd)`
- `goods_receipts(purchase_order_line_id, quantity_received, receipt_date, quality_issue_flag)`
- `monthly_budgets(budget_month, category, revenue_budget_usd, gross_margin_target_pct, operating_expense_budget_usd)`

The backend health check runs a real `SELECT 1` and compares the schema's tables and columns with this contract. `/health` reports `degraded` and `/health/db` returns HTTP 503 with `missing_tables` and `missing_columns` when the database is reachable but the schema is incomplete. Analytics endpoints return HTTP 503 until the full contract is available.

## Verify the connection

From the repository root:

```powershell
$env:PYTHONPATH = 'D:\Project\BizNexa\backend'
.venv\Scripts\python.exe -m uvicorn biznexa.main:app --host 127.0.0.1 --port 8000
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/health/db
curl.exe http://127.0.0.1:8000/api/analytics/synthetic/overview
```

A ready response is reported only after the real query and full schema-contract check succeed. No import command is needed for manually loaded Supabase data.

## Legacy local loader

`backend/scripts/seed_synthetic.py` is retained only as an optional development rebuild tool for a separately supplied CSV package. It is not part of the runtime path and should not be run against the Supabase production project.
