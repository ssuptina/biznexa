# Synthetic dataset

BizNexa uses a PostgreSQL analytics schema for demo data. The app expects a known set of tables and columns, and it checks readiness before serving analytics.

## Expected tables

- `customers`
- `products`
- `sales_orders`
- `sales_order_lines`
- `returns`
- `inventory_snapshots`
- `warehouses`
- `suppliers`
- `purchase_orders`
- `purchase_order_lines`
- `goods_receipts`
- `monthly_budgets`

## Setup

Set local env values:

```env
DATABASE_URL=postgresql+psycopg://...
ANALYTICS_SCHEMA=BizNexa
```

## Verify

```powershell
$env:PYTHONPATH = 'D:\Project\BizNexa\backend'
.venv\Scripts\python.exe -m uvicorn biznexa.main:app --host 127.0.0.1 --port 8000
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/health/db
```

The loader script is optional and should not be used against production data.
