"""Validate and safely load the fictional CSV dataset into biznexa_synthetic.

Validation is read-only. Loading requires an explicit --load flag and a local
development database URL; records are only inserted and never updated/deleted.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "biznexa_data"
REPORT_PATH = ROOT / "reports" / "synthetic-data-validation.json"
SCHEMA = "biznexa_synthetic"
TABLES = {
    "customers": "customer_id",
    "suppliers": "supplier_id",
    "warehouses": "warehouse_id",
    "products": "product_id",
    "sales_orders": "order_id",
    "sales_order_lines": "order_line_id",
    "returns": "return_id",
    "purchase_orders": "purchase_order_id",
    "purchase_order_lines": "purchase_order_line_id",
    "goods_receipts": "receipt_id",
    "inventory_snapshots": ("snapshot_date", "warehouse_id", "product_id"),
    "monthly_budgets": ("budget_month", "category"),
    "service_cases": "case_id",
    "campaigns": "campaign_id",
    "campaign_responses": "campaign_response_id",
}
LOAD_ORDER = tuple(TABLES)
EXPECTED_COUNTS = {
    "customers": 1000, "products": 30, "suppliers": 12, "warehouses": 3,
    "sales_orders": 5886, "sales_order_lines": 11791, "returns": 345,
    "purchase_orders": 393, "purchase_order_lines": 777, "goods_receipts": 641,
    "inventory_snapshots": 2160, "monthly_budgets": 120, "service_cases": 600,
    "campaigns": 12, "campaign_responses": 1200,
}
REFERENCES = (
    ("products", "primary_supplier_id", "suppliers", "supplier_id"),
    ("sales_orders", "customer_id", "customers", "customer_id"),
    ("sales_orders", "warehouse_id", "warehouses", "warehouse_id"),
    ("sales_order_lines", "order_id", "sales_orders", "order_id"),
    ("sales_order_lines", "product_id", "products", "product_id"),
    ("returns", "order_line_id", "sales_order_lines", "order_line_id"),
    ("purchase_orders", "supplier_id", "suppliers", "supplier_id"),
    ("purchase_orders", "warehouse_id", "warehouses", "warehouse_id"),
    ("purchase_order_lines", "purchase_order_id", "purchase_orders", "purchase_order_id"),
    ("purchase_order_lines", "product_id", "products", "product_id"),
    ("goods_receipts", "purchase_order_line_id", "purchase_order_lines", "purchase_order_line_id"),
    ("inventory_snapshots", "warehouse_id", "warehouses", "warehouse_id"),
    ("inventory_snapshots", "product_id", "products", "product_id"),
    ("service_cases", "customer_id", "customers", "customer_id"),
    ("service_cases", "order_id", "sales_orders", "order_id"),
    ("campaign_responses", "campaign_id", "campaigns", "campaign_id"),
    ("campaign_responses", "customer_id", "customers", "customer_id"),
)
DATE_COLUMNS = {"signup_date", "order_date", "return_date", "promised_delivery_date",
                "receipt_date", "snapshot_date", "budget_month", "created_at",
                "start_date", "end_date", "response_date"}
INTEGER_COLUMNS = {"standard_lead_time_days", "payment_terms_days", "reorder_lead_time_days",
                   "minimum_order_qty", "quantity", "quantity_returned", "quantity_ordered",
                   "quantity_received", "on_hand_qty", "reserved_qty", "available_qty",
                   "resolution_days", "satisfaction_score"}
BOOLEAN_COLUMNS = {"email_opt_in", "active_flag", "quality_issue_flag"}
DECIMAL_COLUMNS = {"acquisition_cost_usd", "quality_rating", "unit_cost_usd", "list_price_usd",
                   "unit_price_usd", "discount_pct", "line_revenue_usd", "line_cogs_usd",
                   "refund_amount_usd", "line_cost_usd", "inventory_value_usd",
                   "revenue_budget_usd", "gross_margin_target_pct",
                   "operating_expense_budget_usd", "campaign_cost_usd",
                   "attributed_revenue_usd"}
OPTIONAL_COLUMNS = {"primary_supplier_id", "satisfaction_score"}


def parse_value(column: str, value: str) -> Any:
    if value == "":
        return None
    if column in DATE_COLUMNS:
        return date.fromisoformat(value)
    if column in INTEGER_COLUMNS:
        return int(value)
    if column in BOOLEAN_COLUMNS:
        if value not in ("True", "False"):
            raise ValueError(f"{column}: expected True/False, got {value!r}")
        return value == "True"
    if column in DECIMAL_COLUMNS:
        return Decimal(value)
    return value


def read_data() -> dict[str, list[dict[str, Any]]]:
    data = {}
    for table in LOAD_ORDER:
        path = DATA_DIR / f"{table}.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            data[table] = [{key: parse_value(key, value) for key, value in row.items()}
                           for row in csv.DictReader(handle)]
    return data


def key_tuple(row: dict[str, Any], key: str | tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[col] for col in ((key,) if isinstance(key, str) else key))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true", help="insert validated rows into a local development DB")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    checks: list[dict[str, Any]] = []

    def record(name: str, count: int, *, status: str | None = None, details: str = "") -> None:
        checks.append({"check": name, "count": count, "status": status or ("pass" if count == 0 else "fail"),
                       "details": details})

    try:
        data = read_data()
    except (OSError, ValueError, InvalidOperation, csv.Error) as exc:
        record("CSV parsing", 1, details=str(exc))
        write_report(args.report, checks, {}, loaded=False)
        print(f"Validation could not complete: {exc}", file=sys.stderr)
        return 1

    for table, expected in EXPECTED_COUNTS.items():
        actual = len(data[table])
        record(f"row count: {table}", int(actual != expected),
               details=f"expected {expected}, found {actual}")
        key = TABLES[table]
        seen = Counter(key_tuple(row, key) for row in data[table])
        dupes = [k for k, n in seen.items() if n > 1]
        record(f"duplicate primary keys: {table}", len(dupes), details=f"examples: {dupes[:5]}")
        missing = [(index + 2, column) for index, row in enumerate(data[table])
                   for column, value in row.items() if value is None and column not in OPTIONAL_COLUMNS]
        record(f"required fields present: {table}", len(missing), details=f"examples: {missing[:5]}")

    for child, col, parent, pcol in REFERENCES:
        parent_keys = {row[pcol] for row in data[parent]}
        missing = [row[col] for row in data[child] if row[col] and row[col] not in parent_keys]
        record(f"foreign key: {child}.{col} -> {parent}.{pcol}", len(missing),
               details=f"examples: {missing[:5]}")

    for table, rows in data.items():
        bad_dates = [(index + 2, col, row[col]) for index, row in enumerate(rows)
                     for col in row if col in DATE_COLUMNS and not isinstance(row[col], date)]
        record(f"date parsing: {table}", len(bad_dates), details=f"examples: {bad_dates[:5]}")

    line_by_id = {row["order_line_id"]: row for row in data["sales_order_lines"]}
    po_line_by_id = {row["purchase_order_line_id"]: row for row in data["purchase_order_lines"]}
    bad_revenue = [r for r in data["sales_order_lines"]
                   if abs(r["line_revenue_usd"] - r["quantity"] * r["unit_price_usd"]) > Decimal("0.01")]
    revenue_not_discounted = [r for r in data["sales_order_lines"]
                              if abs(r["line_revenue_usd"] - r["quantity"] * r["unit_price_usd"]
                                     * (Decimal(1) - r["discount_pct"])) > Decimal("0.01")]
    bad_cogs = [r for r in data["sales_order_lines"]
                if abs(r["line_cogs_usd"] - r["quantity"] * r["unit_cost_usd"]) > Decimal("0.01")]
    bad_po = [r for r in data["purchase_order_lines"]
              if abs(r["line_cost_usd"] - r["quantity_ordered"] * r["unit_cost_usd"]) > Decimal("0.01")]
    record("sales line revenue arithmetic", len(bad_revenue), details="expected quantity * unit_price; discount_pct retained separately")
    record("discount field interpretation", len(revenue_not_discounted), status="info",
           details="rows where line_revenue_usd is not quantity * unit_price_usd * (1-discount_pct); discount_pct is not reflected in the provided line revenue arithmetic and needs a business definition before net-sales reporting")
    record("sales line COGS arithmetic", len(bad_cogs), details="expected quantity * sale-time unit_cost")
    record("purchase line cost arithmetic", len(bad_po), details="expected quantity_ordered * unit_cost")

    bad_returns = [r for r in data["returns"] if r["quantity_returned"] > line_by_id[r["order_line_id"]]["quantity"]]
    return_qty: dict[str, int] = defaultdict(int)
    for row in data["returns"]:
        return_qty[row["order_line_id"]] += row["quantity_returned"]
    over_returned = [line for line, quantity in return_qty.items()
                     if quantity > line_by_id[line]["quantity"]]
    record("return event quantity vs sales line", len(bad_returns), details=f"examples: {[r['return_id'] for r in bad_returns[:5]]}")
    record("cumulative returned quantity vs sales line", len(over_returned), details=f"examples: {over_returned[:5]}")

    receipt_qty: dict[str, int] = defaultdict(int)
    bad_receipt_dates = []
    order_by_id = {r["purchase_order_id"]: r for r in data["purchase_orders"]}
    for row in data["goods_receipts"]:
        po_line = po_line_by_id[row["purchase_order_line_id"]]
        receipt_qty[row["purchase_order_line_id"]] += row["quantity_received"]
        po = order_by_id[po_line["purchase_order_id"]]
        if row["receipt_date"] < po["order_date"]:
            bad_receipt_dates.append(row["receipt_id"])
    over_receipts = [line for line, quantity in receipt_qty.items()
                     if quantity > po_line_by_id[line]["quantity_ordered"]]
    record("cumulative received quantity vs PO line", len(over_receipts), details=f"examples: {over_receipts[:5]}")
    record("receipt date on/after PO date", len(bad_receipt_dates), details=f"examples: {bad_receipt_dates[:5]}")

    bad_inventory = [r for r in data["inventory_snapshots"]
                     if r["on_hand_qty"] < 0 or r["reserved_qty"] < 0
                     or r["reserved_qty"] > r["on_hand_qty"]
                     or r["available_qty"] != r["on_hand_qty"] - r["reserved_qty"]]
    bad_inventory_value = [r for r in data["inventory_snapshots"]
                           if r["inventory_value_usd"] < 0 or r["unit_cost_usd"] < 0
                           or abs(r["inventory_value_usd"] - r["on_hand_qty"] * r["unit_cost_usd"]) > Decimal("0.01")]
    record("inventory quantity invariants", len(bad_inventory), details=f"examples: {[r['snapshot_date'].isoformat() + ':' + r['product_id'] for r in bad_inventory[:5]]}")
    record("inventory value = on-hand * unit cost", len(bad_inventory_value), details=f"examples: {[r['snapshot_date'].isoformat() + ':' + r['product_id'] for r in bad_inventory_value[:5]]}")

    bad_campaign_dates = [r["campaign_id"] for r in data["campaigns"] if r["end_date"] < r["start_date"]]
    bad_promised_dates = [r["purchase_order_id"] for r in data["purchase_orders"]
                          if r["promised_delivery_date"] < r["order_date"]]
    record("campaign date order", len(bad_campaign_dates), details=f"examples: {bad_campaign_dates[:5]}")
    record("purchase promised date order", len(bad_promised_dates), details=f"examples: {bad_promised_dates[:5]}")

    orders_by_id = {row["order_id"]: row for row in data["sales_orders"]}
    bad_return_dates = [row["return_id"] for row in data["returns"]
                        if row["return_date"] < orders_by_id[line_by_id[row["order_line_id"]]["order_id"]]["order_date"]]
    bad_case_dates = [row["case_id"] for row in data["service_cases"]
                      if row["created_at"] < orders_by_id[row["order_id"]]["order_date"]]
    bad_budget_dates = [row["budget_month"] for row in data["monthly_budgets"] if row["budget_month"].day != 1]
    record("return date on/after source order", len(bad_return_dates), details=f"examples: {bad_return_dates[:5]}")
    record("service case date on/after source order", len(bad_case_dates), details=f"examples: {bad_case_dates[:5]}")
    record("budget date is first of month", len(bad_budget_dates), details=f"examples: {bad_budget_dates[:5]}")

    constrained = {
        "suppliers.standard_lead_time_days >= 0": sum(r["standard_lead_time_days"] < 0 for r in data["suppliers"]),
        "suppliers.payment_terms_days >= 0": sum(r["payment_terms_days"] < 0 for r in data["suppliers"]),
        "suppliers.quality_rating in [1,5]": sum(not Decimal(1) <= r["quality_rating"] <= Decimal(5) for r in data["suppliers"]),
        "products.reorder_lead_time_days >= 0": sum(r["reorder_lead_time_days"] < 0 for r in data["products"]),
        "products.minimum_order_qty > 0": sum(r["minimum_order_qty"] <= 0 for r in data["products"]),
        "sales_order_lines.quantity > 0": sum(r["quantity"] <= 0 for r in data["sales_order_lines"]),
        "returns.quantity_returned > 0": sum(r["quantity_returned"] <= 0 for r in data["returns"]),
        "purchase_order_lines.quantity_ordered > 0": sum(r["quantity_ordered"] <= 0 for r in data["purchase_order_lines"]),
        "goods_receipts.quantity_received > 0": sum(r["quantity_received"] <= 0 for r in data["goods_receipts"]),
        "monthly_budgets.gross_margin_target_pct in [0,1]": sum(not Decimal(0) <= r["gross_margin_target_pct"] <= Decimal(1) for r in data["monthly_budgets"]),
        "service_cases.resolution_days >= 0": sum(r["resolution_days"] < 0 for r in data["service_cases"]),
    }
    for label, count in constrained.items():
        record(f"schema constraint: {label}", count)

    monetary = {}
    for table, col in (("sales_order_lines", "line_revenue_usd"), ("sales_order_lines", "line_cogs_usd"),
                       ("returns", "refund_amount_usd"), ("purchase_order_lines", "line_cost_usd"),
                       ("inventory_snapshots", "inventory_value_usd"), ("monthly_budgets", "revenue_budget_usd"),
                       ("monthly_budgets", "operating_expense_budget_usd"), ("campaigns", "campaign_cost_usd"),
                       ("campaign_responses", "attributed_revenue_usd")):
        total = sum((row[col] for row in data[table]), Decimal(0))
        monetary[f"{table}.{col}"] = str(total.quantize(Decimal("0.01")))
        negatives = sum(row[col] < 0 for row in data[table])
        record(f"nonnegative monetary values: {table}.{col}", negatives)
    record("discount_pct in [0,1]", sum(not Decimal(0) <= r["discount_pct"] <= Decimal(1) for r in data["sales_order_lines"]))
    record("satisfaction score in [1,5] when present", sum(r["satisfaction_score"] is not None and not 1 <= r["satisfaction_score"] <= 5 for r in data["service_cases"]))

    loaded = False
    loaded_counts: dict[str, int] = {}
    if args.load:
        try:
            loaded_counts = load_data(data)
            loaded = True
            record("database load", 0, details=f"inserted/verified in {SCHEMA}; row counts: {loaded_counts}")
        except Exception as exc:  # noqa: BLE001 - validation report must record every load failure
            record("database load", 1, details=f"rolled back: {type(exc).__name__}: {exc}")

    date_ranges = {}
    for table, rows in data.items():
        for column in rows[0]:
            if column in DATE_COLUMNS:
                values = [row[column] for row in rows if row[column] is not None]
                if values:
                    date_ranges[f"{table}.{column}"] = {"min": min(values).isoformat(), "max": max(values).isoformat()}
    write_report(args.report, checks, monetary, loaded, date_ranges, loaded_counts)
    failed = [item for item in checks if item["status"] == "fail"]
    print(json.dumps({"report": str(args.report), "checks": len(checks), "failed": len(failed),
                      "loaded": loaded, "loaded_row_counts": loaded_counts,
                      "money_totals_usd": monetary}, indent=2))
    return 1 if failed else 0


def load_data(data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    from biznexa.config import get_settings
    settings = get_settings()
    app_env = settings.app_env
    database_url = str(settings.database_url)
    if app_env.lower() != "development" or not database_url:
        raise RuntimeError("--load requires APP_ENV=development and an explicit DATABASE_URL")
    if re.search(r"<[^>]+>", database_url):
        raise RuntimeError("DATABASE_URL contains a placeholder token; set the real Supabase PostgreSQL URL before loading")
    if not settings.synthetic_load_enabled:
        raise RuntimeError("--load requires SYNTHETIC_LOAD_ENABLED=true; use this only for a development database/project")
    from sqlalchemy.engine import make_url
    url = make_url(database_url)
    local_target = url.host in {"localhost", "127.0.0.1", "::1"} and bool(re.search(r"(?:dev|test)", url.database or "", re.IGNORECASE))
    supabase_target = bool(url.host and (url.host.endswith(".supabase.co") or url.host.endswith(".pooler.supabase.com")))
    if not (local_target or supabase_target):
        raise RuntimeError("--load is restricted to localhost dev/test databases or an explicitly enabled Supabase development project")
    import psycopg
    from psycopg import sql

    pg_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    schema_sql = (DATA_DIR / "postgres_schema.sql").read_text(encoding="utf-8-sig")
    schema_sql = schema_sql.replace("CREATE SCHEMA IF NOT EXISTS biznexa;", f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};")
    schema_sql = schema_sql.replace("SET search_path TO biznexa;", f"SET search_path TO {SCHEMA};")
    if "search_path TO biznexa;" in schema_sql:
        raise RuntimeError("could not safely retarget the provided DDL to the synthetic schema")

    loaded_counts: dict[str, int] = {}
    with psycopg.connect(pg_url) as conn, conn.transaction():
            conn.execute(schema_sql)
            for table in LOAD_ORDER:
                rows = data[table]
                columns = list(rows[0])
                key = TABLES[table]
                keys = (key,) if isinstance(key, str) else key
                insert = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                    sql.Identifier(SCHEMA), sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.SQL(",").join(sql.Placeholder() for _ in columns),
                )
                conn.executemany(insert, ([row[col] for col in columns] for row in rows))
                loaded_counts[table] = conn.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(table))
                ).fetchone()[0]
                predicate = sql.SQL(" AND ").join(sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder()) for k in keys)
                select = sql.SQL("SELECT {} FROM {}.{} WHERE ").format(
                    sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(SCHEMA), sql.Identifier(table)
                ) + predicate
                for row in rows:
                    current = conn.execute(select, [row[k] for k in keys]).fetchone()
                    expected = tuple(row[c] for c in columns)
                    if current != expected:
                        raise RuntimeError(f"existing {table} key {key_tuple(row, key)} conflicts with seed values")
    return loaded_counts


def write_report(path: Path, checks: list[dict[str, Any]], totals: dict[str, str], loaded: bool,
                 date_ranges: dict[str, dict[str, str]] | None = None,
                 loaded_counts: dict[str, int] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = [check for check in checks if check["status"] == "fail"]
    observations = [check for check in checks if check["status"] == "info"]
    report = {"dataset": "BizNexa synthetic business dataset", "source": str(DATA_DIR.relative_to(ROOT)),
              "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
              "synthetic_only": True, "database_loaded": loaded,
              "database_row_counts": loaded_counts or {},
              "summary": {"checks": len(checks), "passed": sum(check["status"] == "pass" for check in checks),
                          "failed": len(failures), "observations": len(observations)},
              "date_ranges": date_ranges or {}, "monetary_totals_usd": totals, "checks": checks,
              "inconsistencies": failures, "observations": observations}
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
