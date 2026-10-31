"""Evidence-backed decision intelligence and scenario calculations."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from biznexa import analytics
from biznexa.db import engine

_INACTIVITY_DAYS = 90
_LOW_STOCK_THRESHOLD = 10
_MAX_RELATED_RECORDS = 8


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _format_decimal(value: Decimal | None) -> str | None:
    return str(value.quantize(Decimal("0.0001"))) if value is not None else None


def _pulse_period(
    connection: Any,
    start: str | None,
    end: str | None,
) -> tuple[str, str, str, str]:
    if start is None and end is None:
        _, available_end, available = analytics._bounds_with_available(connection, None, None)
        end_date = date.fromisoformat(available_end)
        start_date = max(
            date.fromisoformat(available["start"]),
            end_date - timedelta(days=364),
        )
        start, end = start_date.isoformat(), available_end
    start_date, end_date, _ = analytics._bounds_with_available(connection, start, end)
    comparison_start, comparison_end = analytics._comparison_bounds(
        start_date, end_date, "previous_period"
    )
    return start_date, end_date, comparison_start, comparison_end


def _insight(
    *,
    insight_id: str,
    title: str,
    category: str,
    level: str,
    metric_name: str,
    metric_value: Any,
    reporting_period: dict[str, str],
    comparison_value: Any | None,
    comparison_period: dict[str, str] | None,
    records: list[dict[str, Any]],
    methodology: str,
    explanation: str,
    next_action: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "id": insight_id,
        "title": title,
        "category": category,
        "level": level,
        "supporting_metric": {
            "name": metric_name,
            "current": str(metric_value),
            "comparison": str(comparison_value) if comparison_value is not None else None,
        },
        "reporting_period": reporting_period,
        "comparison_period": comparison_period,
        "related_records": records,
        "methodology": methodology,
        "explanation": explanation,
        "next_action": next_action,
        "limitations": limitations,
    }


def _build_pulse_insights(
    *,
    period: dict[str, str],
    comparison_period: dict[str, str],
    current: dict[str, Any],
    comparison: dict[str, Any],
    products: list[dict[str, Any]],
    inactive_customers: list[dict[str, Any]],
    inactive_customer_count: int,
    suppliers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    comparison_has_sales = int(comparison["order_count"]) > 0

    current_revenue = _decimal(current["gross_sales_usd"])
    prior_revenue = _decimal(comparison["gross_sales_usd"])
    current_profit = _decimal(current["gross_profit_usd"])
    prior_profit = _decimal(comparison["gross_profit_usd"])
    if comparison_has_sales and current_revenue > 0 and prior_revenue > 0:
        current_margin = current_profit / current_revenue * 100
        prior_margin = prior_profit / prior_revenue * 100
        if current_revenue > prior_revenue and current_margin < prior_margin:
            insights.append(_insight(
                insight_id="revenue-up-margin-down",
                title="Revenue improved while gross margin declined",
                category="Financial Performance",
                level="Review",
                metric_name="Revenue / gross margin",
                metric_value=f"{current_revenue:.2f} / {current_margin:.2f}%",
                comparison_value=f"{prior_revenue:.2f} / {prior_margin:.2f}%",
                reporting_period=period,
                comparison_period=comparison_period,
                records=[{"id": "gross-margin", "name": "Gross margin", "module": "Financial Performance"}],
                methodology="Compare non-cancelled order-line revenue and gross profit in equal-length periods; gross margin is gross profit divided by revenue.",
                explanation=(
                    f"Revenue rose from ${prior_revenue:,.2f} to ${current_revenue:,.2f}, "
                    f"while gross margin fell from {prior_margin:.2f}% to {current_margin:.2f}%."
                ),
                next_action="Review product, category, discount, and cost changes before treating revenue growth as improved profitability.",
                limitations=["Gross profit uses recorded line revenue and cost; operating expenses are not included."],
            ))

    if comparison_has_sales:
        for product in products:
            current_product_revenue = _decimal(product["current_revenue_usd"])
            prior_product_revenue = _decimal(product["comparison_revenue_usd"])
            current_stock_value = product["current_inventory_value_usd"]
            previous_stock_value = product["comparison_inventory_value_usd"]
            if (
                prior_product_revenue > 0
                and current_product_revenue < prior_product_revenue
                and current_stock_value is not None
                and previous_stock_value is not None
                and _decimal(current_stock_value) > _decimal(previous_stock_value)
            ):
                insights.append(_insight(
                    insight_id=f"declining-product-stock-up-{product['product_id']}",
                    title=f"Revenue declined while inventory grew: {product['product_name']}",
                    category="Sales & Inventory",
                    level="Watch",
                    metric_name="Product revenue / inventory value",
                    metric_value=f"{current_product_revenue:.2f} / {_decimal(current_stock_value):.2f}",
                    comparison_value=f"{prior_product_revenue:.2f} / {_decimal(previous_stock_value):.2f}",
                    reporting_period=period,
                    comparison_period=comparison_period,
                    records=[{
                        "id": product["product_id"],
                        "name": product["product_name"],
                        "module": "Inventory & Supply Chain",
                    }],
                    methodology="Compare the product's recorded revenue in equal-length periods and its value in the latest inventory snapshots on or before each period end.",
                    explanation=(
                        f"Revenue changed from ${prior_product_revenue:,.2f} to "
                        f"${current_product_revenue:,.2f}, while inventory value changed "
                        f"from ${_decimal(previous_stock_value):,.2f} to "
                        f"${_decimal(current_stock_value):,.2f}."
                    ),
                    next_action="Review the product's demand, replenishment commitments, and inventory allocation.",
                    limitations=["Inventory values are snapshot values and are not summed over time."],
                ))

            current_units = _decimal(product["current_units_sold"])
            prior_units = _decimal(product["comparison_units_sold"])
            available_qty = product["available_qty"]
            if (
                current_units > prior_units > 0
                and available_qty is not None
                and _decimal(available_qty) < _LOW_STOCK_THRESHOLD
            ):
                insights.append(_insight(
                    insight_id=f"demand-up-stock-low-{product['product_id']}",
                    title=f"Demand rose while available stock is below minimum: {product['product_name']}",
                    category="Sales & Inventory",
                    level="Review",
                    metric_name="Units sold / available units",
                    metric_value=f"{current_units:.0f} / {_decimal(available_qty):.0f}",
                    comparison_value=f"{prior_units:.0f} units sold",
                    reporting_period=period,
                    comparison_period=comparison_period,
                    records=[{
                        "id": product["product_id"],
                        "name": product["product_name"],
                        "module": "Inventory & Supply Chain",
                    }],
                    methodology=f"Require units sold to increase from a nonzero comparison-period baseline and total current available quantity across warehouses to be below the existing {_LOW_STOCK_THRESHOLD}-unit low-stock threshold.",
                    explanation=(
                        f"Units sold increased from {prior_units:.0f} to {current_units:.0f}; "
                        f"company-wide available stock is {_decimal(available_qty):.0f}, below "
                        f"the {_LOW_STOCK_THRESHOLD}-unit alert threshold."
                    ),
                    next_action="Check incoming purchase orders and warehouse availability before approving replenishment.",
                    limitations=["Sales are not adjusted for returns; inventory is the latest snapshot on or before the period end."],
                ))

    if inactive_customer_count:
        shown = inactive_customers[:_MAX_RELATED_RECORDS]
        insights.append(_insight(
            insight_id="high-value-customers-inactive",
            title=f"{inactive_customer_count} high-value customers are inactive",
            category="Customer Intelligence",
            level="Opportunity",
            metric_name="Inactive customers in top lifetime-revenue quartile",
            metric_value=inactive_customer_count,
            comparison_value=None,
            reporting_period=period,
            comparison_period=None,
            records=[{
                "id": row["customer_id"],
                "name": row["customer_name"],
                "module": "Customer Intelligence",
            } for row in shown],
            methodology="Rank customers with positive recorded lifetime sales through the period end by gross sales; high value is the top quartile. Inactive means no non-cancelled purchase in the 90 days ending on the period end.",
            explanation=(
                f"{inactive_customer_count} customers in the top lifetime-revenue quartile "
                f"have no non-cancelled purchase in the 90 days ending {period['end']}."
            ),
            next_action="Review the listed customer histories and consider a measured retention outreach.",
            limitations=[
                f"At most {_MAX_RELATED_RECORDS} customer records are listed.",
                "Lifetime ranking uses recorded gross line revenue and does not subtract returns.",
            ],
        ))

    late_suppliers = [row for row in suppliers if int(row["late_lines"]) > 0]
    if late_suppliers:
        late_count = sum(int(row["late_lines"]) for row in late_suppliers)
        received_count = sum(int(row["received_lines"]) for row in late_suppliers)
        insights.append(_insight(
            insight_id="supplier-late-receipts",
            title=f"{late_count} received purchase-order lines arrived late",
            category="Supplier Intelligence",
            level="Review",
            metric_name="Late / completed receipt lines",
            metric_value=late_count,
            comparison_value=None,
            reporting_period=period,
            comparison_period=None,
            records=[{
                "id": row["supplier_id"],
                "name": row["supplier_name"],
                "module": "Inventory & Supply Chain",
            } for row in late_suppliers[:_MAX_RELATED_RECORDS]],
            methodology="Count fully received purchase-order lines whose last receipt date is after the promised delivery date; purchase orders are filtered by order date.",
            explanation=f"{late_count} of {received_count} completed receipt lines in the selected order-date period were received after their promised dates.",
            next_action="Review delivery performance with the listed suppliers and confirm current replenishment coverage.",
            limitations=[
                "Only completed lines with a promised delivery date and receipt date are scored.",
                "Purchase-order lines do not identify a product in this schema, so late deliveries are not attributed to specific inventory shortages.",
            ],
        ))

    return insights


def business_pulse(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    with engine.connect() as connection:
        analytics._schema_guard(connection)
        start_date, end_date, comparison_start, comparison_end = _pulse_period(
            connection, start, end
        )
        parameters = {
            "start_date": start_date,
            "end_date": end_date,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
            "inactive_cutoff": (
                date.fromisoformat(end_date) - timedelta(days=_INACTIVITY_DAYS)
            ).isoformat(),
        }
        totals = analytics._rows(connection.execute(text(f"""
            SELECT CASE WHEN o.order_date BETWEEN CAST(:start_date AS date)
                                              AND CAST(:end_date AS date)
                        THEN 'current' ELSE 'comparison' END AS period_kind,
                   SUM(l.line_revenue_usd) AS gross_sales_usd,
                   SUM(l.line_cogs_usd) AS cogs_usd,
                   SUM(l.line_revenue_usd - l.line_cogs_usd) AS gross_profit_usd,
                   COUNT(DISTINCT o.order_id) AS order_count
            FROM {analytics.SCHEMA}.sales_orders o
            JOIN {analytics.SCHEMA}.sales_order_lines l USING (order_id)
            WHERE o.order_status <> 'Cancelled'
              AND (o.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
                   OR o.order_date BETWEEN CAST(:comparison_start AS date)
                                       AND CAST(:comparison_end AS date))
            GROUP BY period_kind
        """), parameters))
        total_by_period = {
            row["period_kind"]: row for row in totals
        }
        current = total_by_period.get("current", {
            "gross_sales_usd": 0, "cogs_usd": 0, "gross_profit_usd": 0, "order_count": 0,
        })
        comparison = total_by_period.get("comparison", {
            "gross_sales_usd": 0, "cogs_usd": 0, "gross_profit_usd": 0, "order_count": 0,
        })
        products = analytics._rows(connection.execute(text(f"""
            WITH sales AS (
              SELECT l.product_id,
                     COALESCE(SUM(l.line_revenue_usd) FILTER (
                       WHERE o.order_date BETWEEN CAST(:start_date AS date)
                                              AND CAST(:end_date AS date)
                     ), 0) AS current_revenue_usd,
                     COALESCE(SUM(l.line_revenue_usd) FILTER (
                       WHERE o.order_date BETWEEN CAST(:comparison_start AS date)
                                              AND CAST(:comparison_end AS date)
                     ), 0) AS comparison_revenue_usd,
                     COALESCE(SUM(l.quantity) FILTER (
                       WHERE o.order_date BETWEEN CAST(:start_date AS date)
                                              AND CAST(:end_date AS date)
                     ), 0) AS current_units_sold,
                     COALESCE(SUM(l.quantity) FILTER (
                       WHERE o.order_date BETWEEN CAST(:comparison_start AS date)
                                              AND CAST(:comparison_end AS date)
                     ), 0) AS comparison_units_sold
              FROM {analytics.SCHEMA}.sales_orders o
              JOIN {analytics.SCHEMA}.sales_order_lines l USING (order_id)
              WHERE o.order_status <> 'Cancelled'
                AND (o.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
                     OR o.order_date BETWEEN CAST(:comparison_start AS date)
                                         AND CAST(:comparison_end AS date))
              GROUP BY l.product_id
            ), snapshot_dates AS (
              SELECT MAX(snapshot_date) FILTER (
                       WHERE snapshot_date <= CAST(:end_date AS date)
                     ) AS current_snapshot,
                     MAX(snapshot_date) FILTER (
                       WHERE snapshot_date <= CAST(:comparison_end AS date)
                     ) AS comparison_snapshot
              FROM {analytics.SCHEMA}.inventory_snapshots
            ), stock AS (
              SELECT i.product_id,
                     SUM(i.inventory_value_usd) FILTER (
                       WHERE i.snapshot_date = d.current_snapshot
                     ) AS current_inventory_value_usd,
                     SUM(i.inventory_value_usd) FILTER (
                       WHERE i.snapshot_date = d.comparison_snapshot
                     ) AS comparison_inventory_value_usd,
                     SUM(i.available_qty) FILTER (
                       WHERE i.snapshot_date = d.current_snapshot
                     ) AS available_qty,
                     MAX(i.snapshot_date) FILTER (
                       WHERE i.snapshot_date = d.current_snapshot
                     ) AS current_snapshot,
                     MAX(d.comparison_snapshot) AS comparison_snapshot
              FROM {analytics.SCHEMA}.inventory_snapshots i
              CROSS JOIN snapshot_dates d
              GROUP BY i.product_id
            )
            SELECT p.product_id, p.product_name,
                   COALESCE(s.current_revenue_usd, 0) AS current_revenue_usd,
                   COALESCE(s.comparison_revenue_usd, 0) AS comparison_revenue_usd,
                   COALESCE(s.current_units_sold, 0) AS current_units_sold,
                   COALESCE(s.comparison_units_sold, 0) AS comparison_units_sold,
                   stock.current_inventory_value_usd,
                   stock.comparison_inventory_value_usd,
                   stock.available_qty,
                   stock.current_snapshot,
                   stock.comparison_snapshot
            FROM {analytics.SCHEMA}.products p
            LEFT JOIN sales s USING (product_id)
            LEFT JOIN stock USING (product_id)
        """), parameters))
        inactive_customers = analytics._rows(connection.execute(text(f"""
            WITH customer_activity AS (
              SELECT c.customer_id, c.customer_name,
                     MAX(o.order_date) AS last_purchase,
                     COALESCE(SUM(l.line_revenue_usd), 0) AS lifetime_sales_usd
              FROM {analytics.SCHEMA}.customers c
              LEFT JOIN {analytics.SCHEMA}.sales_orders o
                ON o.customer_id = c.customer_id
               AND o.order_status <> 'Cancelled'
               AND o.order_date <= CAST(:end_date AS date)
              LEFT JOIN {analytics.SCHEMA}.sales_order_lines l USING (order_id)
              GROUP BY c.customer_id, c.customer_name
            ), ranked AS (
              SELECT customer_activity.*,
                     NTILE(4) OVER (ORDER BY lifetime_sales_usd DESC, customer_id) AS value_quartile
              FROM customer_activity
              WHERE lifetime_sales_usd > 0
            )
            SELECT customer_id, customer_name, last_purchase, lifetime_sales_usd
            FROM ranked
            WHERE value_quartile = 1
              AND (last_purchase IS NULL OR last_purchase < CAST(:inactive_cutoff AS date))
            ORDER BY lifetime_sales_usd DESC, customer_id
        """), parameters))
        suppliers = analytics._rows(connection.execute(text(f"""
            WITH receipts AS (
              SELECT pol.purchase_order_line_id, po.supplier_id,
                     po.promised_delivery_date, SUM(gr.quantity_received) AS received_qty,
                     MAX(gr.receipt_date) FILTER (
                       WHERE gr.receipt_date <= CAST(:end_date AS date)
                     ) AS last_receipt_date
              FROM {analytics.SCHEMA}.purchase_orders po
              JOIN {analytics.SCHEMA}.purchase_order_lines pol USING (purchase_order_id)
              LEFT JOIN {analytics.SCHEMA}.goods_receipts gr USING (purchase_order_line_id)
              WHERE po.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
              GROUP BY pol.purchase_order_line_id, po.supplier_id, po.promised_delivery_date
            )
            SELECT s.supplier_id, s.supplier_name,
                   COUNT(*) FILTER (
                     WHERE COALESCE(r.received_qty, 0) >= pol.quantity_ordered
                       AND r.promised_delivery_date IS NOT NULL
                       AND r.last_receipt_date IS NOT NULL
                   ) AS received_lines,
                   COUNT(*) FILTER (
                     WHERE COALESCE(r.received_qty, 0) >= pol.quantity_ordered
                       AND r.promised_delivery_date IS NOT NULL
                       AND r.last_receipt_date > r.promised_delivery_date
                   ) AS late_lines
            FROM {analytics.SCHEMA}.suppliers s
            LEFT JOIN receipts r USING (supplier_id)
            LEFT JOIN {analytics.SCHEMA}.purchase_order_lines pol
              USING (purchase_order_line_id)
            GROUP BY s.supplier_id, s.supplier_name
            ORDER BY late_lines DESC, s.supplier_name
        """), parameters))

    period = {"start": start_date, "end": end_date}
    comparison_period = {"start": comparison_start, "end": comparison_end}
    insights = _build_pulse_insights(
        period=period,
        comparison_period=comparison_period,
        current=current,
        comparison=comparison,
        products=products,
        inactive_customers=inactive_customers,
        inactive_customer_count=len(inactive_customers),
        suppliers=suppliers,
    )
    current_inventory_values = [
        _decimal(row["current_inventory_value_usd"])
        for row in products if row["current_inventory_value_usd"] is not None
    ]
    comparison_inventory_values = [
        _decimal(row["comparison_inventory_value_usd"])
        for row in products if row["comparison_inventory_value_usd"] is not None
    ]
    current_inventory_snapshot = next(
        (row["current_snapshot"] for row in products if row["current_snapshot"] is not None),
        None,
    )
    comparison_inventory_snapshot = next(
        (row["comparison_snapshot"] for row in products if row["comparison_snapshot"] is not None),
        None,
    )
    current_margin = (
        _decimal(current["gross_profit_usd"]) / _decimal(current["gross_sales_usd"]) * 100
        if _decimal(current["gross_sales_usd"]) else None
    )
    comparison_margin = (
        _decimal(comparison["gross_profit_usd"]) / _decimal(comparison["gross_sales_usd"]) * 100
        if _decimal(comparison["gross_sales_usd"]) else None
    )
    return {
        "synthetic": True,
        "period": period,
        "comparison_period": comparison_period,
        "comparison_available": int(comparison["order_count"]) > 0,
        "summary": {
            "current": {
                "gross_sales_usd": _format_decimal(_decimal(current["gross_sales_usd"])),
                "gross_profit_usd": _format_decimal(_decimal(current["gross_profit_usd"])),
                "gross_margin_pct": _format_decimal(current_margin),
                "order_count": int(current["order_count"]),
                "inventory_value_usd": _format_decimal(sum(current_inventory_values, Decimal(0))),
                "low_stock_product_count": sum(
                    1 for row in products
                    if row["available_qty"] is not None
                    and _decimal(row["available_qty"]) < _LOW_STOCK_THRESHOLD
                ),
                "inventory_snapshot_date": current_inventory_snapshot,
            },
            "comparison": {
                "gross_sales_usd": _format_decimal(_decimal(comparison["gross_sales_usd"])),
                "gross_profit_usd": _format_decimal(_decimal(comparison["gross_profit_usd"])),
                "gross_margin_pct": _format_decimal(comparison_margin),
                "order_count": int(comparison["order_count"]),
                "inventory_value_usd": (
                    _format_decimal(sum(comparison_inventory_values, Decimal(0)))
                    if comparison_inventory_snapshot is not None else None
                ),
                "inventory_snapshot_date": comparison_inventory_snapshot,
            },
        },
        "method": "Evidence rules over recorded PostgreSQL aggregates. No predictive model or causal claim is used.",
        "insights": insights,
        "data_limitations": [
            "Temporal comparisons use equal-length periods and are omitted when the comparison period has no sales records.",
            "Supplier purchase-order lines do not identify products, so supplier delays are not attributed to specific stock shortages.",
        ],
    }


def _calculate_scenario(
    baseline: dict[str, Any],
    assumptions: dict[str, Decimal | None],
) -> dict[str, Any]:
    revenue = _decimal(baseline["gross_sales_usd"])
    cogs = _decimal(baseline["cogs_usd"])
    customer_count = int(baseline["customer_count"])
    inventory_value = (
        _decimal(baseline["inventory_value_usd"])
        if baseline["inventory_value_usd"] is not None else None
    )
    sales_growth = _decimal(assumptions["sales_growth_pct"]) / 100
    cost_change = _decimal(assumptions["product_cost_change_pct"]) / 100
    retention_change = _decimal(assumptions["retention_change_pct"]) / 100
    inventory_change = _decimal(assumptions["inventory_change_pct"]) / 100
    avg_revenue_per_customer = (
        revenue / customer_count if customer_count else Decimal(0)
    )
    retention_revenue = (
        avg_revenue_per_customer * customer_count * retention_change
    )
    projected_revenue = revenue * (1 + sales_growth) + retention_revenue
    projected_cogs = cogs * (1 + cost_change)
    projected_profit = projected_revenue - projected_cogs
    projected_margin = (
        projected_profit / projected_revenue * 100 if projected_revenue else None
    )
    margin_target = assumptions["gross_margin_target_pct"]
    target_profit = (
        projected_revenue * _decimal(margin_target) / 100
        if margin_target is not None else None
    )

    return {
        "baseline_period": baseline["period"],
        "actual_baseline": {
            "gross_sales_usd": baseline["gross_sales_usd"],
            "cogs_usd": baseline["cogs_usd"],
            "gross_profit_usd": baseline["gross_profit_usd"],
            "gross_margin_pct": baseline["gross_margin_pct"],
            "order_count": baseline["order_count"],
            "customer_count": customer_count,
            "average_revenue_per_customer_usd": baseline["average_revenue_per_customer_usd"],
            "inventory_value_usd": baseline["inventory_value_usd"],
            "inventory_snapshot_date": baseline["inventory_snapshot_date"],
        },
        "assumptions": {
            key: _format_decimal(value) for key, value in assumptions.items()
        },
        "scenario": {
            "projected_revenue_usd": _format_decimal(projected_revenue),
            "retention_revenue_change_usd": _format_decimal(retention_revenue),
            "projected_cogs_usd": _format_decimal(projected_cogs),
            "projected_gross_profit_usd": _format_decimal(projected_profit),
            "projected_gross_margin_pct": _format_decimal(projected_margin),
            "projected_inventory_value_usd": (
                _format_decimal(inventory_value * (1 + inventory_change))
                if inventory_value is not None else None
            ),
            "gross_profit_at_target_margin_usd": _format_decimal(target_profit),
            "target_margin_profit_gap_usd": (
                _format_decimal(target_profit - projected_profit)
                if target_profit is not None else None
            ),
        },
        "formulas": [
            "Projected revenue = baseline revenue × (1 + sales growth) + baseline average revenue per customer × baseline customers × retention change.",
            "Projected COGS = baseline COGS × (1 + product cost change).",
            "Projected gross profit = projected revenue − projected COGS; projected margin = projected gross profit ÷ projected revenue.",
            "Projected inventory value = latest baseline inventory value × (1 + inventory change).",
            "Target-margin gross profit = projected revenue × target gross margin; the gap compares this target with cost-adjusted projected gross profit.",
        ],
        "limitations": [
            "This is deterministic scenario arithmetic, not a forecast or prediction.",
            "Retention uplift applies the assumed percentage change to the baseline period's average revenue per customer; it does not model customer-level behavior.",
            "Inventory value is shown separately and is not assumed to convert directly into sales.",
            "No business records are modified.",
        ],
    }


def what_if_scenario(
    assumptions: dict[str, Decimal | None],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    with engine.connect() as connection:
        analytics._schema_guard(connection)
        start_date, end_date, _, _ = _pulse_period(connection, start, end)
        baseline = analytics._one(connection.execute(text(f"""
            SELECT COALESCE(SUM(l.line_revenue_usd), 0) AS gross_sales_usd,
                   COALESCE(SUM(l.line_cogs_usd), 0) AS cogs_usd,
                   COALESCE(SUM(l.line_revenue_usd - l.line_cogs_usd), 0)
                     AS gross_profit_usd,
                   COUNT(DISTINCT o.order_id) AS order_count,
                   COUNT(DISTINCT o.customer_id) AS customer_count
            FROM {analytics.SCHEMA}.sales_orders o
            JOIN {analytics.SCHEMA}.sales_order_lines l USING (order_id)
            WHERE o.order_status <> 'Cancelled'
              AND o.order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
        """), {"start_date": start_date, "end_date": end_date}))
        inventory = analytics._one(connection.execute(text(f"""
            WITH latest AS (
              SELECT MAX(snapshot_date) AS snapshot_date
              FROM {analytics.SCHEMA}.inventory_snapshots
              WHERE snapshot_date <= CAST(:end_date AS date)
            )
            SELECT latest.snapshot_date,
                   SUM(i.inventory_value_usd) AS inventory_value_usd
            FROM latest
            LEFT JOIN {analytics.SCHEMA}.inventory_snapshots i USING (snapshot_date)
            GROUP BY latest.snapshot_date
        """), {"end_date": end_date}))

    gross_sales = _decimal(baseline["gross_sales_usd"])
    gross_profit = _decimal(baseline["gross_profit_usd"])
    customer_count = int(baseline["customer_count"])
    baseline.update({
        "period": {"start": start_date, "end": end_date},
        "gross_margin_pct": (
            _format_decimal(gross_profit / gross_sales * 100)
            if gross_sales else None
        ),
        "average_revenue_per_customer_usd": (
            _format_decimal(gross_sales / customer_count)
            if customer_count else _format_decimal(Decimal(0))
        ),
        "inventory_value_usd": _format_decimal(
            _decimal(inventory["inventory_value_usd"])
        ) if inventory["inventory_value_usd"] is not None else None,
        "inventory_snapshot_date": inventory["snapshot_date"],
    })
    result = _calculate_scenario(baseline, assumptions)
    result["synthetic"] = True
    result["has_sales_data"] = int(baseline["order_count"]) > 0
    return result
