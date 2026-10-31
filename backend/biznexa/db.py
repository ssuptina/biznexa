import re
from collections.abc import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from biznexa.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_SCHEMA_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ANALYTICS_SCHEMA_CONTRACT = {
    "customers": {"customer_id", "customer_name"},
    "goods_receipts": {
        "purchase_order_line_id",
        "quantity_received",
        "receipt_date",
        "quality_issue_flag",
    },
    "inventory_snapshots": {
        "snapshot_date",
        "warehouse_id",
        "product_id",
        "on_hand_qty",
        "reserved_qty",
        "available_qty",
        "unit_cost_usd",
        "inventory_value_usd",
    },
    "monthly_budgets": {
        "budget_month",
        "category",
        "revenue_budget_usd",
        "gross_margin_target_pct",
        "operating_expense_budget_usd",
    },
    "products": {"product_id", "product_name", "category", "minimum_order_qty"},
    "purchase_order_lines": {
        "purchase_order_line_id",
        "purchase_order_id",
        "quantity_ordered",
        "line_cost_usd",
    },
    "purchase_orders": {
        "purchase_order_id",
        "supplier_id",
        "order_date",
        "promised_delivery_date",
    },
    "returns": {"order_line_id", "return_date", "refund_amount_usd"},
    "sales_order_lines": {
        "order_id",
        "order_line_id",
        "product_id",
        "quantity",
        "line_revenue_usd",
        "line_cogs_usd",
    },
    "sales_orders": {"order_id", "customer_id", "order_date", "order_status"},
    "suppliers": {"supplier_id", "supplier_name", "quality_rating"},
    "warehouses": {"warehouse_id", "warehouse_name"},
}


def is_valid_schema_identifier(schema: str) -> bool:
    return bool(_SCHEMA_PATTERN.fullmatch(schema.strip()))


def _missing_analytics_schema_items(
    actual_columns: Iterable[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    actual = set(actual_columns)
    actual_tables = {table for table, _ in actual}
    missing_tables = sorted(_ANALYTICS_SCHEMA_CONTRACT.keys() - actual_tables)
    missing_columns = sorted(
        f"{table}.{column}"
        for table, columns in _ANALYTICS_SCHEMA_CONTRACT.items()
        if table in actual_tables
        for column in columns
        if (table, column) not in actual
    )
    return missing_tables, missing_columns


def database_health() -> dict[str, object]:
    """Run a real database query without exposing credentials or driver errors."""
    settings = get_settings()
    if not settings.database_url:
        return {"status": "not_configured", "detail": "DATABASE_URL is not configured."}
    if "<" in settings.database_url or ">" in settings.database_url:
        return {"status": "invalid_config", "detail": "DATABASE_URL still contains a placeholder token; set the real Supabase PostgreSQL URL."}
    schema = settings.analytics_schema.strip()
    if not is_valid_schema_identifier(schema):
        return {"status": "invalid_config", "detail": "ANALYTICS_SCHEMA must be a simple PostgreSQL schema identifier."}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            actual_columns = connection.execute(
                text(
                    "SELECT table_name, column_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :schema"
                ),
                {"schema": schema.lower()},
            ).tuples().all()
        missing_tables, missing_columns = _missing_analytics_schema_items(actual_columns)
        schema_initialized = not missing_tables and not missing_columns
        return {
            "status": "ok",
            "query": "SELECT 1",
            "analytics_schema": schema,
            "analytics_schema_initialized": schema_initialized,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
        }
    except SQLAlchemyError as exc:
        message = str(exc).splitlines()[0]
        if "getaddrinfo failed" in message.lower() or "failed to resolve host" in message.lower():
            return {
                "status": "error",
                "error_type": "dns",
                "detail": (
                    "The PostgreSQL hostname in DATABASE_URL could not be resolved. "
                    "Verify the Supabase host, or use the Session Pooler URI from Supabase Connect "
                    "for local IPv4 environments."
                ),
                "technical_detail": message[:300],
            }
        return {"status": "error", "detail": message[:300]}
