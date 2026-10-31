"""Read-only analytics queries over the configured PostgreSQL schema.

Every metric in this module uses the imported BizNexa table contract. Canceled orders are excluded from sales,
returns are reported separately, and inventory is always selected at the latest
snapshot date rather than summed across dates.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from biznexa.config import get_settings
from biznexa.db import engine, is_valid_schema_identifier

SCHEMA = get_settings().analytics_schema.strip()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in result.mappings()]


def _one(result: Any) -> dict[str, Any]:
    row = result.mappings().one()
    return {key: _json_value(value) for key, value in row.items()}


def _schema_guard(connection: Any) -> None:
    if not is_valid_schema_identifier(SCHEMA):
        raise RuntimeError(
            "ANALYTICS_SCHEMA must be a simple PostgreSQL schema identifier."
        )
    exists = connection.execute(
        text("SELECT to_regclass(:table_name)"),
        {"table_name": f"{SCHEMA}.sales_orders"},
    ).scalar_one_or_none()
    if exists is None:
        raise RuntimeError(
            f"Database is reachable, but schema {SCHEMA!r} does not contain sales_orders. "
            "Set ANALYTICS_SCHEMA to the schema containing the imported Supabase tables."
        )


def _bounds_with_available(
    connection: Any,
    start: str | None,
    end: str | None,
) -> tuple[str, str, dict[str, str]]:
    if start is not None:
        date.fromisoformat(start)
    if end is not None:
        date.fromisoformat(end)
    row = _one(connection.execute(text(f"""
        SELECT MIN(order_date) AS available_start,
               MAX(order_date) AS available_end,
               COALESCE(CAST(:start_date AS date), MIN(order_date)) AS start_date,
               COALESCE(CAST(:end_date AS date), MAX(order_date)) AS end_date
        FROM {SCHEMA}.sales_orders
    """), {"start_date": start, "end_date": end}))
    if row["available_start"] is None or row["available_end"] is None:
        raise RuntimeError(f"Schema {SCHEMA!r} contains no sales order dates.")
    if row["start_date"] > row["end_date"]:
        raise ValueError("start_date must be on or before end_date")
    return row["start_date"], row["end_date"], {
        "start": row["available_start"],
        "end": row["available_end"],
    }


def _bounds(connection: Any, start: str | None, end: str | None) -> tuple[str, str]:
    start_date, end_date, _ = _bounds_with_available(connection, start, end)
    return start_date, end_date


def _comparison_bounds(start: str, end: str, comparison: str) -> tuple[str, str]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if comparison == "same_period_last_year":
        def previous_year(value: date) -> date:
            year = value.year - 1
            return value.replace(year=year, day=min(value.day, monthrange(year, value.month)[1]))

        return previous_year(start_date).isoformat(), previous_year(end_date).isoformat()
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - (end_date - start_date)
    return previous_start.isoformat(), previous_end.isoformat()


def _category_drivers(
    categories: list[dict[str, Any]],
    category_months: list[dict[str, Any]],
    gross_sales: Decimal,
) -> list[dict[str, Any]]:
    if gross_sales <= 0:
        return []

    drivers = []
    for category in categories[:3]:
        monthly_sales = [
            row for row in category_months if row["category"] == category["category"]
        ]
        if not monthly_sales:
            continue
        best_month = max(
            monthly_sales, key=lambda row: Decimal(row["gross_sales_usd"])
        )
        category_sales = Decimal(category["gross_sales_usd"])
        drivers.append({
            "category": category["category"],
            "gross_sales_usd": str(category_sales),
            "contribution_pct": str(category_sales / gross_sales * Decimal(100)),
            "best_month": best_month["month"],
            "best_month_gross_sales_usd": str(Decimal(best_month["gross_sales_usd"])),
        })
    return drivers


def _overview_sales_aggregates(
    connection: Any,
    start: str,
    end: str,
    comparison_start: str | None,
    comparison_end: str | None,
    granularity: str,
    include_daily_sales: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]],
           list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _rows(connection.execute(text(f"""
        WITH order_lines AS (
          SELECT CASE WHEN o.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
                      THEN 'current' ELSE 'comparison' END AS period_kind,
                 o.order_id, o.customer_id, o.order_date,
                 date_trunc(:granularity, o.order_date)::date AS trend_period,
                 date_trunc('month', o.order_date)::date AS month_period,
                 date_trunc('quarter', o.order_date)::date AS quarter_period,
                 EXTRACT(DOW FROM o.order_date)::integer AS weekday,
                 to_char(o.order_date, 'FMDay') AS weekday_name,
                 l.line_revenue_usd, l.line_cogs_usd
          FROM {SCHEMA}.sales_orders o
          JOIN {SCHEMA}.sales_order_lines l USING (order_id)
          WHERE o.order_status <> 'Cancelled'
            AND (
              o.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
              OR (
                CAST(:comparison_start AS date) IS NOT NULL
                AND o.order_date BETWEEN CAST(:comparison_start AS date) AND CAST(:comparison_end AS date)
              )
            )
        ), aggregate_rows AS (
          SELECT CASE
                   WHEN GROUPING(trend_period) = 0 THEN 'trend'
                   WHEN GROUPING(month_period) = 0 THEN 'month'
                   WHEN GROUPING(quarter_period) = 0 THEN 'quarter'
                   WHEN GROUPING(weekday) = 0 THEN 'weekday'
                   WHEN GROUPING(order_date) = 0 THEN 'daily'
                   ELSE 'totals'
                 END AS aggregate_type,
                 period_kind, trend_period, month_period, quarter_period,
                 weekday, weekday_name, order_date,
                 SUM(line_revenue_usd) AS gross_sales_usd,
                 SUM(line_revenue_usd - line_cogs_usd) AS gross_profit_usd,
                 SUM(line_cogs_usd) AS cogs_usd,
                 COUNT(DISTINCT order_id) AS order_count,
                 COUNT(DISTINCT customer_id) AS customer_count
          FROM order_lines
          GROUP BY GROUPING SETS (
            (period_kind),
            (period_kind, trend_period),
            (period_kind, month_period),
            (period_kind, quarter_period),
            (period_kind, weekday, weekday_name),
            (period_kind, order_date)
          )
        ), ranked_daily AS (
          SELECT aggregate_rows.*,
                 ROW_NUMBER() OVER (ORDER BY gross_sales_usd DESC, order_date) AS sales_rank,
                 ROW_NUMBER() OVER (ORDER BY order_count DESC, order_date) AS orders_rank
          FROM aggregate_rows
          WHERE aggregate_type = 'daily' AND period_kind = 'current'
        )
        SELECT aggregate_type, period_kind, trend_period, month_period, quarter_period,
               weekday, weekday_name, order_date, gross_sales_usd, gross_profit_usd,
               cogs_usd, order_count, customer_count,
               FALSE AS is_sales_peak, FALSE AS is_orders_peak
        FROM aggregate_rows
        WHERE aggregate_type <> 'daily'
          AND (period_kind = 'current' OR aggregate_type = 'totals')
        UNION ALL
        SELECT aggregate_type, period_kind, trend_period, month_period, quarter_period,
               weekday, weekday_name, order_date, gross_sales_usd, gross_profit_usd,
               cogs_usd, order_count, customer_count,
               sales_rank = 1 AS is_sales_peak, orders_rank = 1 AS is_orders_peak
        FROM ranked_daily
        WHERE CAST(:include_daily_sales AS boolean) OR sales_rank = 1 OR orders_rank = 1
        ORDER BY aggregate_type, period_kind, trend_period NULLS LAST, month_period NULLS LAST,
                 quarter_period NULLS LAST, weekday NULLS LAST, order_date NULLS LAST
    """), {
        "start_date": start,
        "end_date": end,
        "comparison_start": comparison_start,
        "comparison_end": comparison_end,
        "granularity": granularity,
        "include_daily_sales": include_daily_sales,
    }))
    current = next((row for row in rows if row["aggregate_type"] == "totals" and row["period_kind"] == "current"), {})
    comparison = next((row for row in rows if row["aggregate_type"] == "totals" and row["period_kind"] == "comparison"), {})
    totals = {
        "gross_sales_usd": current.get("gross_sales_usd", "0"),
        "gross_profit_usd": current.get("gross_profit_usd", "0"),
        "cogs_usd": current.get("cogs_usd", "0"),
        "order_count": current.get("order_count", 0),
        "customer_count": current.get("customer_count", 0),
    }
    comparison_totals = {
        "gross_sales_usd": comparison.get("gross_sales_usd", "0"),
        "gross_profit_usd": comparison.get("gross_profit_usd", "0"),
        "order_count": comparison.get("order_count", 0),
    }
    trend_rows = sorted(
        (row for row in rows if row["aggregate_type"] == "trend" and row["period_kind"] == "current"),
        key=lambda row: row["trend_period"],
    )
    trend = [{
        "period": row["trend_period"],
        "gross_sales_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
        "order_count": row["order_count"],
    } for row in trend_rows]
    daily = [{
        "date": row["order_date"],
        "gross_sales_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
        "order_count": row["order_count"],
        "is_sales_peak": row["is_sales_peak"],
        "is_orders_peak": row["is_orders_peak"],
    } for row in rows if row["aggregate_type"] == "daily"]
    weekday_rows = sorted(
        (row for row in rows if row["aggregate_type"] == "weekday" and row["period_kind"] == "current"),
        key=lambda row: row["weekday"],
    )
    weekdays = [{
        "weekday": row["weekday"],
        "weekday_name": row["weekday_name"],
        "gross_sales_usd": row["gross_sales_usd"],
        "order_count": row["order_count"],
    } for row in weekday_rows]
    monthly_rows = sorted(
        (row for row in rows if row["aggregate_type"] == "month" and row["period_kind"] == "current"),
        key=lambda row: row["month_period"],
    )
    monthly = [{
        "month": row["month_period"],
        "gross_sales_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
        "order_count": row["order_count"],
    } for row in monthly_rows]
    quarter_aggregate_rows = sorted(
        (row for row in rows if row["aggregate_type"] == "quarter" and row["period_kind"] == "current"),
        key=lambda row: row["quarter_period"],
    )
    quarter_rows = [{
        "period": row["quarter_period"],
        "gross_sales_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
    } for row in quarter_aggregate_rows]
    return totals, comparison_totals, trend, daily, weekdays, monthly, quarter_rows


def _overview_product_aggregates(
    connection: Any,
    start: str,
    end: str,
    product_limit: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _rows(connection.execute(text(f"""
        WITH product_aggregates AS (
          SELECT CASE
                   WHEN GROUPING(product_id) = 0 THEN 'product'
                   WHEN GROUPING(month_period) = 0 THEN 'category_month'
                   ELSE 'category'
                 END AS aggregate_type,
                 category, month_period, product_id, product_name,
                 SUM(line_revenue_usd) AS gross_sales_usd,
                 SUM(line_revenue_usd - line_cogs_usd) AS gross_profit_usd,
                 SUM(quantity) AS units_sold
          FROM (
            SELECT p.category, p.product_id, p.product_name,
                   date_trunc('month', o.order_date)::date AS month_period,
                   l.line_revenue_usd, l.line_cogs_usd, l.quantity
            FROM {SCHEMA}.sales_orders o
            JOIN {SCHEMA}.sales_order_lines l USING (order_id)
            JOIN {SCHEMA}.products p USING (product_id)
            WHERE o.order_status <> 'Cancelled'
              AND o.order_date BETWEEN :start_date AND :end_date
          ) sales
          GROUP BY GROUPING SETS (
            (category),
            (category, month_period),
            (product_id, product_name, category)
          )
        ), ranked_products AS (
          SELECT product_aggregates.*,
                 ROW_NUMBER() OVER (ORDER BY gross_sales_usd DESC) AS revenue_rank
          FROM product_aggregates
          WHERE aggregate_type = 'product'
          ORDER BY gross_sales_usd DESC
          LIMIT :product_limit
        )
        SELECT aggregate_type, category, month_period, product_id, product_name,
               gross_sales_usd, gross_profit_usd, units_sold
        FROM product_aggregates
        WHERE aggregate_type <> 'product'
        UNION ALL
        SELECT aggregate_type, category, month_period, product_id, product_name,
               gross_sales_usd, gross_profit_usd, units_sold
        FROM ranked_products
        WHERE revenue_rank <= :product_limit
        ORDER BY aggregate_type, category, month_period NULLS LAST, gross_sales_usd DESC
    """), {"start_date": start, "end_date": end, "product_limit": product_limit}))
    category_rows = sorted(
        (row for row in rows if row["aggregate_type"] == "category"),
        key=lambda row: Decimal(row["gross_sales_usd"]),
        reverse=True,
    )
    categories = [{
        "category": row["category"],
        "gross_sales_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
    } for row in category_rows]
    category_months = [{
        "category": row["category"],
        "month": row["month_period"],
        "gross_sales_usd": row["gross_sales_usd"],
    } for row in rows if row["aggregate_type"] == "category_month"]
    top_products = sorted(({
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "category": row["category"],
        "revenue_usd": row["gross_sales_usd"],
        "gross_profit_usd": row["gross_profit_usd"],
        "units_sold": row["units_sold"],
    } for row in rows if row["aggregate_type"] == "product"),
        key=lambda row: Decimal(row["revenue_usd"]),
        reverse=True,
    )
    return categories, category_months, top_products


def overview(
    start: str | None = None,
    end: str | None = None,
    granularity: str = "month",
    comparison: str = "previous_period",
    include_daily_sales: bool = True,
) -> dict[str, Any]:
    if granularity not in {"day", "week", "month", "quarter", "year"}:
        raise ValueError("granularity must be day, week, month, quarter, or year")
    if comparison not in {"previous_period", "same_period_last_year", "none"}:
        raise ValueError("comparison must be previous_period, same_period_last_year, or none")
    with engine.connect() as connection:
        _schema_guard(connection)
        start_date, end_date, available_period = _bounds_with_available(connection, start, end)
        comparison_start, comparison_end = (
            _comparison_bounds(start_date, end_date, comparison)
            if comparison != "none" else (None, None)
        )
        (
            totals, comparison_totals, trend, daily, weekdays, monthly, quarter_rows,
        ) = _overview_sales_aggregates(
            connection,
            start_date,
            end_date,
            comparison_start,
            comparison_end,
            granularity,
            include_daily_sales,
        )
        refunds = _one(connection.execute(text(f"""
            SELECT COALESCE(SUM(r.refund_amount_usd), 0) AS refunds_usd
            FROM {SCHEMA}.returns r
            JOIN {SCHEMA}.sales_order_lines l USING (order_line_id)
            JOIN {SCHEMA}.sales_orders o USING (order_id)
            WHERE o.order_status <> 'Cancelled'
              AND r.return_date BETWEEN :start_date AND :end_date
        """), {"start_date": start_date, "end_date": end_date}))
        categories, category_months, top_products = _overview_product_aggregates(
            connection, start_date, end_date
        )
        inventory = _one(connection.execute(text(f"""
            WITH latest AS (SELECT MAX(snapshot_date) AS snapshot_date
                            FROM {SCHEMA}.inventory_snapshots
                            WHERE snapshot_date <= CAST(:as_of AS date))
            SELECT latest.snapshot_date,
                   COALESCE(SUM(i.inventory_value_usd), 0) AS inventory_value_usd,
                   COUNT(*) FILTER (WHERE i.available_qty < 10) AS low_stock_count
            FROM latest
            LEFT JOIN {SCHEMA}.inventory_snapshots i USING (snapshot_date)
            GROUP BY latest.snapshot_date
        """), {"as_of": end_date}))
        customer_segments = _rows(connection.execute(text(f"""
            WITH activity AS (
              SELECT c.customer_id, MAX(o.order_date) AS last_purchase,
                     COUNT(DISTINCT o.order_id) AS order_count
              FROM {SCHEMA}.customers c
              LEFT JOIN {SCHEMA}.sales_orders o ON o.customer_id = c.customer_id
                   AND o.order_status <> 'Cancelled' AND o.order_date <= :as_of
              GROUP BY c.customer_id
            )
            SELECT CASE WHEN last_purchase IS NULL OR last_purchase < :cutoff THEN 'Inactive'
                        WHEN order_count >= 2 THEN 'Repeat' ELSE 'New or one-time' END AS segment,
                   COUNT(*) AS customers
            FROM activity
            GROUP BY 1 ORDER BY customers DESC
        """), {"cutoff": (date.fromisoformat(end_date) - timedelta(days=90)).isoformat(), "as_of": end_date}))
        comparison_has_data = comparison != "none" and int(comparison_totals["order_count"]) > 0

    gross = Decimal(totals["gross_sales_usd"])
    profit = Decimal(totals["gross_profit_usd"])
    orders = int(totals["order_count"])
    comparison_gross = Decimal(comparison_totals["gross_sales_usd"])
    comparison_profit = Decimal(comparison_totals["gross_profit_usd"])
    comparison_orders = int(comparison_totals["order_count"])
    sales_change = ((gross - comparison_gross) / comparison_gross * 100) if comparison_gross else None
    profit_change = ((profit - comparison_profit) / comparison_profit * 100) if comparison_profit else None
    order_change = ((orders - comparison_orders) / comparison_orders * 100) if comparison_orders else None
    category_leader = {
        "category": categories[0]["category"],
        "gross_sales_usd": categories[0]["gross_sales_usd"],
    } if categories else None
    category_drivers = _category_drivers(categories, category_months, gross)
    highest_revenue_month = max(monthly, key=lambda row: Decimal(row["gross_sales_usd"]), default=None)
    highest_profit_month = max(monthly, key=lambda row: Decimal(row["gross_profit_usd"]), default=None)
    lowest_month = min(monthly, key=lambda row: Decimal(row["gross_sales_usd"]), default=None)
    highest_revenue_month = {
        key: value for key, value in highest_revenue_month.items() if key != "order_count"
    } if highest_revenue_month else None
    highest_profit_month = {
        key: value for key, value in highest_profit_month.items() if key != "order_count"
    } if highest_profit_month else None
    lowest_month = {
        key: value for key, value in lowest_month.items() if key != "order_count"
    } if lowest_month else None
    sales_peak = next((row for row in daily if row["is_sales_peak"]), None)
    orders_peak = next((row for row in daily if row["is_orders_peak"]), None)
    highest_sales_day = {
        key: value for key, value in sales_peak.items()
        if key not in {"is_sales_peak", "is_orders_peak"}
    } if sales_peak else None
    highest_order_day = {
        key: value for key, value in orders_peak.items()
        if key not in {"is_sales_peak", "is_orders_peak"}
    } if orders_peak else None
    best_weekday = max(weekdays, key=lambda row: Decimal(row["gross_sales_usd"]), default=None)
    strongest_quarter = max(quarter_rows, key=lambda row: Decimal(row["gross_sales_usd"]), default=None)
    days_in_period = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
    average_daily_revenue = gross / days_in_period if days_in_period > 0 else Decimal(0)
    daily_series = []
    if include_daily_sales:
        daily_by_date = {row["date"]: row for row in daily}
        current_date = max(date.fromisoformat(start_date), date.fromisoformat(available_period["start"]))
        last_date = min(date.fromisoformat(end_date), date.fromisoformat(available_period["end"]))
        while current_date <= last_date:
            day = daily_by_date.get(current_date.isoformat())
            daily_series.append({
                "date": current_date.isoformat(),
                "gross_sales_usd": day["gross_sales_usd"] if day else "0",
                "gross_profit_usd": day["gross_profit_usd"] if day else "0",
                "order_count": day["order_count"] if day else 0,
            })
            current_date += timedelta(days=1)
    inactive_count = next((int(row["customers"]) for row in customer_segments if row["segment"] == "Inactive"), 0)
    low_stock_count = int(inventory["low_stock_count"] or 0)
    actions = []
    if low_stock_count:
        actions.append({"id": "inventory-low-stock", "priority": "High", "title": "Review low-stock items",
                        "entity": "Inventory", "impact": 0, "owner": "Inventory manager", "due": "Review next cycle",
                        "status": "Needs review", "evidence": f"{low_stock_count} items are below 10 available units.",
                        "assumption": "Reorder quantities require supplier and demand review."})
    if inactive_count:
        actions.append({"id": "customer-inactivity", "priority": "Medium", "title": "Review inactive customers",
                        "entity": "Customers", "impact": 0, "owner": "Customer manager", "due": "Review next cycle",
                        "status": "Needs review", "evidence": f"{inactive_count} customers have no purchase in 90 days.",
                        "assumption": "Inactivity is a screening rule, not a trained churn prediction."})
    return {
        "dataset": "BizNexa synthetic dataset",
        "synthetic": True,
        "currency": "USD",
        "sales_policy": "Canceled orders excluded; revenue and COGS are before return adjustments.",
        "return_policy": "Refunds are reported separately and are not subtracted from gross profit.",
        "reporting_period": {"start": start_date, "end": end_date},
        "available_period": available_period,
        "gross_sales_usd": str(gross),
        "gross_profit_before_returns_usd": str(profit),
        "gross_margin_pct": str((profit / gross * 100) if gross else Decimal(0)),
        "refunds_usd": refunds["refunds_usd"],
        "net_sales_after_refunds_usd": str(gross - Decimal(refunds["refunds_usd"])),
        "order_count": orders,
        "has_sales_records": orders > 0,
        "customer_count": int(totals["customer_count"]),
        "repeat_customer_count": int(next((row["customers"] for row in customer_segments if row["segment"] == "Repeat"), 0)),
        "inactive_customer_count": inactive_count,
        "churn_rule": "Inactive means no non-canceled purchase in the prior 90 days.",
        "customer_segments": customer_segments,
        "average_order_value_usd": str(gross / orders if orders else Decimal(0)),
        "period_over_period_change_pct": str(sales_change) if sales_change is not None else None,
        "comparison": {
            "type": comparison,
            "start": comparison_start,
            "end": comparison_end,
            "has_data": comparison_has_data,
            "gross_sales_usd": str(comparison_gross),
            "gross_profit_before_returns_usd": str(comparison_profit),
            "order_count": comparison_orders,
            "gross_sales_change_usd": str(gross - comparison_gross) if comparison_has_data else None,
            "gross_sales_change_pct": str(sales_change) if comparison_has_data and sales_change is not None else None,
            "gross_profit_change_usd": str(profit - comparison_profit) if comparison_has_data else None,
            "gross_profit_change_pct": str(profit_change) if comparison_has_data and profit_change is not None else None,
            "order_count_change": orders - comparison_orders if comparison_has_data else None,
            "order_count_change_pct": str(order_change) if comparison_has_data and order_change is not None else None,
        },
        "latest_inventory_snapshot": inventory["snapshot_date"],
        "latest_inventory_value_usd": inventory["inventory_value_usd"],
        "low_stock_count": low_stock_count,
        "top_products": [{
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "category": row["category"],
            "revenue_usd": row["revenue_usd"],
        } for row in top_products],
        "actions": actions,
        "granularity": granularity,
        "trend": [{
            "period": row["period"],
            "gross_sales_usd": row["gross_sales_usd"],
            "gross_profit_before_returns_usd": row["gross_profit_usd"],
            "order_count": row["order_count"],
        } for row in trend],
        "daily_sales": daily_series,
        "weekday_sales": weekdays,
        "highlights": {
            "highest_revenue_month": highest_revenue_month,
            "highest_profit_month": highest_profit_month,
            "lowest_revenue_month": lowest_month,
            "highest_sales_day": {
                **highest_sales_day,
                "average_daily_revenue_usd": str(average_daily_revenue),
                "change_vs_average_usd": str(Decimal(highest_sales_day["gross_sales_usd"]) - average_daily_revenue),
            } if highest_sales_day else None,
            "highest_order_day": highest_order_day,
            "best_weekday": best_weekday,
            "best_category": category_leader,
            "strongest_quarter": strongest_quarter,
        },
        "monthly": [{
            "month": row["month"],
            "gross_sales_usd": row["gross_sales_usd"],
            "gross_profit_before_returns_usd": row["gross_profit_usd"],
        } for row in monthly],
        "categories": [{"category": row["category"], "gross_sales_usd": row["gross_sales_usd"]} for row in categories],
        "category_drivers": category_drivers,
        "last_refreshed": date.today().isoformat(),
    }


def sales(start: str | None = None, end: str | None = None, granularity: str = "month") -> dict[str, Any]:
    if granularity not in {"day", "week", "month", "quarter", "year"}:
        raise ValueError("granularity must be day, week, month, quarter, or year")
    with engine.connect() as connection:
        _schema_guard(connection)
        start_date, end_date = _bounds(connection, start, end)
        _, _, trend, _, _, monthly, _ = _overview_sales_aggregates(
            connection, start_date, end_date, None, None, granularity, False
        )
        categories, _, products = _overview_product_aggregates(
            connection, start_date, end_date, product_limit=20
        )
    return {"synthetic": True, "reporting_period": {"start": start_date, "end": end_date},
            "granularity": granularity,
            "trend": [{
                "period": row["period"],
                "revenue_usd": row["gross_sales_usd"],
                "gross_profit_usd": row["gross_profit_usd"],
                "order_count": row["order_count"],
            } for row in trend],
            "monthly": [{
                "month": row["month"],
                "revenue_usd": row["gross_sales_usd"],
                "gross_profit_usd": row["gross_profit_usd"],
                "order_count": row["order_count"],
            } for row in monthly],
            "categories": [{
                "category": row["category"],
                "revenue_usd": row["gross_sales_usd"],
                "gross_profit_usd": row["gross_profit_usd"],
            } for row in categories],
            "top_products": products}


def customers(as_of: str | None = None, inactivity_days: int = 90) -> dict[str, Any]:
    if inactivity_days < 1 or inactivity_days > 3650:
        raise ValueError("inactivity_days must be between 1 and 3650")
    with engine.connect() as connection:
        _schema_guard(connection)
        max_date = _one(connection.execute(text(f"SELECT MAX(order_date) AS as_of FROM {SCHEMA}.sales_orders"))) ["as_of"]
        as_of_date = as_of or max_date
        if as_of_date is None:
            raise RuntimeError("No sales order dates are available to establish the customer analysis date.")
        date.fromisoformat(as_of_date)
        cutoff = (date.fromisoformat(as_of_date) - timedelta(days=inactivity_days)).isoformat()
        summary = _one(connection.execute(text(f"""
            WITH customer_activity AS (
              SELECT c.customer_id, c.customer_name, MAX(o.order_date) AS last_purchase,
                     COUNT(DISTINCT o.order_id) AS order_count,
                     SUM(l.line_revenue_usd) AS revenue_usd
              FROM {SCHEMA}.customers c
              LEFT JOIN {SCHEMA}.sales_orders o ON o.customer_id = c.customer_id
                   AND o.order_status <> 'Cancelled' AND o.order_date <= :as_of
              LEFT JOIN {SCHEMA}.sales_order_lines l USING (order_id)
              GROUP BY c.customer_id, c.customer_name
            )
            SELECT COUNT(*) AS customer_count,
                   COUNT(*) FILTER (WHERE order_count >= 2) AS repeat_customers,
                   COUNT(*) FILTER (WHERE last_purchase < :cutoff OR last_purchase IS NULL) AS inactive_customers,
                   COALESCE(AVG(order_count) FILTER (WHERE order_count > 0), 0) AS avg_orders_per_buyer,
                   COALESCE(SUM(revenue_usd), 0) AS revenue_usd
            FROM customer_activity
        """), {"cutoff": cutoff, "as_of": as_of_date}))
        segments = _rows(connection.execute(text(f"""
            WITH activity AS (
              SELECT c.customer_id, c.customer_name, MAX(o.order_date) AS last_purchase,
                     COUNT(DISTINCT o.order_id) AS order_count,
                     COALESCE(SUM(l.line_revenue_usd), 0) AS revenue_usd
              FROM {SCHEMA}.customers c
              LEFT JOIN {SCHEMA}.sales_orders o ON o.customer_id = c.customer_id
                   AND o.order_status <> 'Cancelled' AND o.order_date <= :as_of
              LEFT JOIN {SCHEMA}.sales_order_lines l USING (order_id)
              GROUP BY c.customer_id, c.customer_name
            )
            SELECT CASE WHEN last_purchase IS NULL OR last_purchase < :cutoff THEN 'Inactive'
                        WHEN order_count >= 2 THEN 'Repeat' ELSE 'New or one-time' END AS segment,
                   COUNT(*) AS customers, COALESCE(SUM(revenue_usd), 0) AS revenue_usd
            FROM activity GROUP BY 1 ORDER BY customers DESC
        """), {"cutoff": cutoff, "as_of": as_of_date}))
    return {"synthetic": True, "as_of": as_of_date, "inactivity_days": inactivity_days,
            "churn_rule": f"Inactive means no non-canceled purchase in the prior {inactivity_days} days.",
            "summary": summary, "segments": segments}


def finance(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    with engine.connect() as connection:
        _schema_guard(connection)
        start_date, end_date = _bounds(connection, start, end)
        rows = _rows(connection.execute(text(f"""
            WITH actual AS (
              SELECT date_trunc('month', o.order_date)::date AS month,
                     p.category, SUM(l.line_revenue_usd) AS revenue_usd,
                     SUM(l.line_revenue_usd - l.line_cogs_usd) AS gross_profit_usd
              FROM {SCHEMA}.sales_orders o JOIN {SCHEMA}.sales_order_lines l USING (order_id)
              JOIN {SCHEMA}.products p USING (product_id)
              WHERE o.order_status <> 'Cancelled' AND o.order_date BETWEEN :start_date AND :end_date
              GROUP BY 1, 2
            )
            SELECT COALESCE(a.month, b.budget_month) AS month,
                   COALESCE(a.category, b.category) AS category,
                   COALESCE(a.revenue_usd, 0) AS actual_revenue_usd,
                   COALESCE(a.gross_profit_usd, 0) AS actual_gross_profit_usd,
                   COALESCE(b.revenue_budget_usd, 0) AS revenue_budget_usd,
                   COALESCE(b.gross_margin_target_pct, 0) AS gross_margin_target_pct,
                   COALESCE(b.operating_expense_budget_usd, 0) AS operating_expense_budget_usd
            FROM actual a FULL OUTER JOIN {SCHEMA}.monthly_budgets b
              ON b.budget_month = a.month AND b.category = a.category
            WHERE COALESCE(a.month, b.budget_month) BETWEEN :start_date AND :end_date
            ORDER BY 1, 2
        """), {"start_date": start_date, "end_date": end_date}))
    for row in rows:
        actual = Decimal(row["actual_revenue_usd"])
        budget = Decimal(row["revenue_budget_usd"])
        row["variance_usd"] = str(actual - budget)
        row["variance_pct"] = _variance_percent(actual, budget)
        row["actual_margin_pct"] = str((Decimal(row["actual_gross_profit_usd"]) / actual * 100) if actual else Decimal(0))
    return {"synthetic": True, "reporting_period": {"start": start_date, "end": end_date}, "monthly": rows}


def _variance_percent(actual: Decimal, budget: Decimal) -> str | None:
    if budget == 0:
        return None
    return str((actual - budget) / budget * 100)


def inventory(as_of: str | None = None, low_stock_threshold: int = 10) -> dict[str, Any]:
    with engine.connect() as connection:
        _schema_guard(connection)
        if as_of is not None:
            date.fromisoformat(as_of)
        snapshot = _one(connection.execute(text(f"""
            SELECT MAX(snapshot_date) AS snapshot_date
            FROM {SCHEMA}.inventory_snapshots
            WHERE snapshot_date <= COALESCE(
                CAST(:as_of AS date),
                (SELECT MAX(snapshot_date) FROM {SCHEMA}.inventory_snapshots)
            )
        """), {"as_of": as_of}))["snapshot_date"]
        rows = _rows(connection.execute(text(f"""
            SELECT i.snapshot_date, i.warehouse_id, w.warehouse_name, i.product_id,
                   p.product_name, p.category, i.on_hand_qty, i.reserved_qty, i.available_qty,
                   i.unit_cost_usd, i.inventory_value_usd, p.minimum_order_qty
            FROM {SCHEMA}.inventory_snapshots i
            JOIN {SCHEMA}.warehouses w USING (warehouse_id)
            JOIN {SCHEMA}.products p USING (product_id)
            WHERE i.snapshot_date = :snapshot_date
            ORDER BY i.available_qty ASC, i.inventory_value_usd DESC
        """), {"snapshot_date": snapshot}))
    for row in rows:
        row["low_stock"] = int(row["available_qty"]) < low_stock_threshold
        row["reorder_recommended"] = row["low_stock"]
        row["recommended_order_qty"] = row["minimum_order_qty"] if row["low_stock"] else 0
    return {"synthetic": True, "snapshot_date": snapshot, "low_stock_threshold": low_stock_threshold,
            "inventory_value_usd": str(sum((Decimal(r["inventory_value_usd"]) for r in rows), Decimal(0))),
            "low_stock_count": sum(r["low_stock"] for r in rows), "items": rows}


def suppliers(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    if start is not None:
        date.fromisoformat(start)
    if end is not None:
        date.fromisoformat(end)
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be on or before end_date")
    date_filter = ""
    date_parameters: dict[str, Any] = {}
    if start is not None or end is not None:
        date_filter = (
            "AND po.order_date BETWEEN "
            "COALESCE(CAST(:start_date AS date), DATE '0001-01-01') "
            "AND COALESCE(CAST(:end_date AS date), DATE '9999-12-31')"
        )
        date_parameters = {"start_date": start, "end_date": end}
    with engine.connect() as connection:
        _schema_guard(connection)
        rows = _rows(connection.execute(text(f"""
            WITH receipt AS (
              SELECT pol.purchase_order_line_id, SUM(gr.quantity_received) AS received_qty,
                     MAX(gr.receipt_date) AS last_receipt_date,
                     BOOL_OR(gr.quality_issue_flag) AS quality_issue
              FROM {SCHEMA}.purchase_order_lines pol
              LEFT JOIN {SCHEMA}.goods_receipts gr USING (purchase_order_line_id)
              GROUP BY pol.purchase_order_line_id
            )
            SELECT s.supplier_id, s.supplier_name, s.quality_rating,
                   COUNT(DISTINCT po.purchase_order_id) AS purchase_orders,
                   COALESCE(SUM(pol.line_cost_usd), 0) AS purchase_value_usd,
                   COUNT(*) FILTER (
                     WHERE COALESCE(receipt.received_qty, 0) >= pol.quantity_ordered
                       AND po.promised_delivery_date IS NOT NULL
                       AND receipt.last_receipt_date IS NOT NULL
                   ) AS received_lines,
                   COUNT(*) FILTER (
                     WHERE COALESCE(receipt.received_qty, 0) >= pol.quantity_ordered
                       AND po.promised_delivery_date IS NOT NULL
                       AND receipt.last_receipt_date <= po.promised_delivery_date
                   ) AS on_time_lines,
                   COUNT(*) FILTER (
                     WHERE COALESCE(receipt.received_qty, 0) >= pol.quantity_ordered
                       AND po.promised_delivery_date IS NOT NULL
                       AND receipt.last_receipt_date > po.promised_delivery_date
                   ) AS late_lines,
                   COALESCE(AVG(receipt.last_receipt_date - po.promised_delivery_date)
                     FILTER (
                       WHERE COALESCE(receipt.received_qty, 0) >= pol.quantity_ordered
                         AND po.promised_delivery_date IS NOT NULL
                         AND receipt.last_receipt_date IS NOT NULL
                     ), 0) AS avg_delay_days,
                   COUNT(*) FILTER (WHERE receipt.quality_issue) AS quality_issue_lines
            FROM {SCHEMA}.suppliers s
            LEFT JOIN {SCHEMA}.purchase_orders po
              ON po.supplier_id = s.supplier_id {date_filter}
            LEFT JOIN {SCHEMA}.purchase_order_lines pol USING (purchase_order_id)
            LEFT JOIN receipt USING (purchase_order_line_id)
            GROUP BY s.supplier_id, s.supplier_name, s.quality_rating
            ORDER BY late_lines DESC, quality_issue_lines DESC, purchase_value_usd DESC
        """), date_parameters))
    for row in rows:
        row["on_time_rate_pct"] = _supplier_on_time_rate_percent(
            int(row["on_time_lines"]), int(row["received_lines"])
        )
        row["risk"] = "High" if int(row["late_lines"]) > 0 or int(row["quality_issue_lines"]) > 0 else "Normal"
    return {"synthetic": True, "suppliers": rows}


def _supplier_on_time_rate_percent(on_time_lines: int, received_lines: int) -> str | None:
    if received_lines == 0:
        return None
    return str(Decimal(on_time_lines) / Decimal(received_lines) * Decimal(100))


def decisions(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    if start is not None:
        date.fromisoformat(start)
    if end is not None:
        date.fromisoformat(end)
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be on or before end_date")
    inv = inventory(as_of=end)
    cust = customers(as_of=end)
    actions: list[dict[str, Any]] = []
    if inv["low_stock_count"]:
        actions.append({"id": "inventory-low-stock", "priority": "High", "title": "Review low-stock items",
                        "reason": f"{inv['low_stock_count']} product/warehouse records are below the configured availability threshold.",
                        "supporting_metric": inv["low_stock_count"], "suggested_action": "Approve replenishment quantities using the latest snapshot."})
    inactive = int(cust["summary"]["inactive_customers"])
    if inactive:
        actions.append({"id": "customer-inactivity", "priority": "Medium", "title": "Review inactive customers",
                        "reason": cust["churn_rule"], "supporting_metric": inactive,
                        "suggested_action": "Prioritize a retention or win-back test and measure subsequent purchases."})
    return {"synthetic": True, "reporting_period": {"start": start, "end": end}, "actions": actions,
            "method": "Threshold-based recommendations from validated query results; no predictive model is claimed."}
