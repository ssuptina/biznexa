"""Persistence and descriptive outcome review for recorded business decisions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select, text

from biznexa import analytics
from biznexa.db import SessionLocal, engine
from biznexa.models import BusinessDecision

METRICS = {
    "gross_sales_usd": {
        "label": "Gross sales", "unit": "USD",
        "methodology": "Sum of sales line revenue for non-cancelled orders in the period.",
    },
    "gross_profit_usd": {
        "label": "Gross profit", "unit": "USD",
        "methodology": "Sum of sales line revenue minus line cost for non-cancelled orders.",
    },
    "gross_margin_pct": {
        "label": "Gross margin", "unit": "%",
        "methodology": "Gross profit divided by gross sales, multiplied by 100.",
    },
    "order_count": {
        "label": "Order count", "unit": "orders",
        "methodology": "Distinct non-cancelled order IDs in the period.",
    },
    "inventory_value_usd": {
        "label": "Inventory value", "unit": "USD",
        "methodology": "Sum of recorded inventory value at the latest snapshot in the period.",
    },
    "low_stock_count": {
        "label": "Low-stock locations", "unit": "locations",
        "methodology": "Count of product/warehouse snapshot rows with fewer than 10 available units at the latest snapshot.",
    },
    "supplier_on_time_rate_pct": {
        "label": "Supplier on-time rate", "unit": "%",
        "methodology": "Percentage of fully received, date-promised purchase-order lines placed in the period and completed by period end that were received on or before their promised date.",
    },
}


class DecisionTrackerNotFound(Exception):
    pass


class ReviewDataUnavailable(Exception):
    pass


def _rounded_metric(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _decision_periods(decision_date: date, review_after_days: int) -> tuple[date, date, date, date]:
    try:
        return (
            decision_date - timedelta(days=review_after_days),
            decision_date - timedelta(days=1),
            decision_date + timedelta(days=1),
            decision_date + timedelta(days=review_after_days),
        )
    except OverflowError as exc:
        raise ValueError("The decision date and review window must fit supported calendar dates.") from exc


def _available_bounds() -> dict[str, tuple[date, date] | None]:
    with engine.connect() as connection:
        analytics._schema_guard(connection)
        row = analytics._one(connection.execute(text(f"""
            SELECT
              (SELECT MIN(order_date) FROM {analytics.SCHEMA}.sales_orders) AS sales_start,
              (SELECT MAX(order_date) FROM {analytics.SCHEMA}.sales_orders) AS sales_end,
              (SELECT MIN(snapshot_date) FROM {analytics.SCHEMA}.inventory_snapshots) AS inventory_start,
              (SELECT MAX(snapshot_date) FROM {analytics.SCHEMA}.inventory_snapshots) AS inventory_end,
              (SELECT MIN(order_date) FROM {analytics.SCHEMA}.purchase_orders) AS supplier_start,
              (SELECT MAX(order_date) FROM {analytics.SCHEMA}.purchase_orders) AS supplier_end
        """)))
    result: dict[str, tuple[date, date] | None] = {}
    for key in ("sales", "inventory", "supplier"):
        start = row[f"{key}_start"]
        end = row[f"{key}_end"]
        result[key] = (
            (date.fromisoformat(start), date.fromisoformat(end))
            if start is not None and end is not None else None
        )
    return result


def _metric_source(metric_key: str) -> str:
    if metric_key in {"inventory_value_usd", "low_stock_count"}:
        return "inventory"
    if metric_key == "supplier_on_time_rate_pct":
        return "supplier"
    return "sales"


def _metric_value(
    metric_key: str,
    start: date,
    end: date,
) -> tuple[Decimal | None, str | None]:
    if start > end:
        raise ValueError("metric period start must be on or before end")
    if metric_key not in METRICS:
        raise ValueError("Unsupported decision metric.")

    with engine.connect() as connection:
        analytics._schema_guard(connection)
        if metric_key in {
            "gross_sales_usd", "gross_profit_usd", "gross_margin_pct", "order_count",
        }:
            bounds = analytics._one(connection.execute(text(f"""
                SELECT MIN(order_date) AS available_start, MAX(order_date) AS available_end
                FROM {analytics.SCHEMA}.sales_orders
            """)))
            available_start = date.fromisoformat(bounds["available_start"]) if bounds["available_start"] else None
            available_end = date.fromisoformat(bounds["available_end"]) if bounds["available_end"] else None
            if (
                available_start is None
                or available_end is None
                or start < available_start
                or end > available_end
            ):
                return None, "The complete metric period is outside the available sales data."
            values = analytics._one(connection.execute(text(f"""
                SELECT COALESCE(SUM(l.line_revenue_usd), 0) AS gross_sales_usd,
                       COALESCE(SUM(l.line_revenue_usd - l.line_cogs_usd), 0)
                         AS gross_profit_usd,
                       COUNT(DISTINCT o.order_id) AS order_count
                FROM {analytics.SCHEMA}.sales_orders o
                JOIN {analytics.SCHEMA}.sales_order_lines l USING (order_id)
                WHERE o.order_status <> 'Cancelled'
                  AND o.order_date BETWEEN :start_date AND :end_date
            """), {"start_date": start, "end_date": end}))
            if metric_key == "gross_sales_usd":
                return _rounded_metric(values["gross_sales_usd"]), None
            if metric_key == "gross_profit_usd":
                return _rounded_metric(values["gross_profit_usd"]), None
            if metric_key == "order_count":
                return _rounded_metric(values["order_count"]), None
            revenue = Decimal(values["gross_sales_usd"])
            if not revenue:
                return None, "Gross margin is undefined because the period has no recorded sales."
            return _rounded_metric(Decimal(values["gross_profit_usd"]) / revenue * 100), None

        if metric_key in {"inventory_value_usd", "low_stock_count"}:
            snapshot = analytics._one(connection.execute(text(f"""
                SELECT MAX(snapshot_date) AS snapshot_date
                FROM {analytics.SCHEMA}.inventory_snapshots
                WHERE snapshot_date BETWEEN :start_date AND :end_date
            """), {"start_date": start, "end_date": end}))["snapshot_date"]
            if snapshot is None:
                return None, "No inventory snapshot exists in the selected metric period."
            values = analytics._one(connection.execute(text(f"""
                SELECT COALESCE(SUM(inventory_value_usd), 0) AS inventory_value_usd,
                       COUNT(*) FILTER (WHERE available_qty < 10) AS low_stock_count
                FROM {analytics.SCHEMA}.inventory_snapshots
                WHERE snapshot_date = :snapshot_date
            """), {"snapshot_date": snapshot}))
            value = (
                values["inventory_value_usd"]
                if metric_key == "inventory_value_usd"
                else values["low_stock_count"]
            )
            return _rounded_metric(value), None

        bounds = analytics._one(connection.execute(text(f"""
            SELECT MIN(order_date) AS available_start, MAX(order_date) AS available_end
            FROM {analytics.SCHEMA}.purchase_orders
        """)))
        available_start = date.fromisoformat(bounds["available_start"]) if bounds["available_start"] else None
        available_end = date.fromisoformat(bounds["available_end"]) if bounds["available_end"] else None
        if (
            available_start is None
            or available_end is None
            or start < available_start
            or end > available_end
        ):
            return None, "The complete metric period is outside the available purchase-order data."
        values = analytics._one(connection.execute(text(f"""
            WITH receipt AS (
              SELECT pol.purchase_order_line_id, po.promised_delivery_date,
                     pol.quantity_ordered,
                     SUM(gr.quantity_received) FILTER (
                       WHERE gr.receipt_date <= :end_date
                     ) AS received_qty,
                     MAX(gr.receipt_date) FILTER (
                       WHERE gr.receipt_date <= :end_date
                     ) AS last_receipt_date
              FROM {analytics.SCHEMA}.purchase_orders po
              JOIN {analytics.SCHEMA}.purchase_order_lines pol USING (purchase_order_id)
              LEFT JOIN {analytics.SCHEMA}.goods_receipts gr USING (purchase_order_line_id)
              WHERE po.order_date BETWEEN :start_date AND :end_date
              GROUP BY pol.purchase_order_line_id, po.promised_delivery_date,
                       pol.quantity_ordered
            )
            SELECT COUNT(*) FILTER (
                     WHERE COALESCE(received_qty, 0) >= quantity_ordered
                       AND promised_delivery_date IS NOT NULL
                       AND last_receipt_date IS NOT NULL
                   ) AS completed_lines,
                   COUNT(*) FILTER (
                     WHERE COALESCE(received_qty, 0) >= quantity_ordered
                       AND promised_delivery_date IS NOT NULL
                       AND last_receipt_date <= promised_delivery_date
                   ) AS on_time_lines
            FROM receipt
        """), {"start_date": start, "end_date": end}))
        completed = int(values["completed_lines"])
        if completed == 0:
            return None, "No completed, date-promised receipt lines exist in the selected period."
        return _rounded_metric(Decimal(values["on_time_lines"]) / Decimal(completed) * 100), None


def _record_payload(
    record: BusinessDecision,
    available_bounds: dict[str, tuple[date, date] | None],
) -> dict[str, Any]:
    _, _, review_start, review_end = _decision_periods(
        record.decision_date, record.review_after_days
    )
    bounds = available_bounds[_metric_source(record.metric_key)]
    reviewable = (
        record.reviewed_at is None
        and bounds is not None
        and review_start >= bounds[0]
        and review_end <= bounds[1]
    )
    return {
        "id": record.id,
        "title": record.title,
        "expected_outcome": record.expected_outcome,
        "decision_date": record.decision_date.isoformat(),
        "metric_key": record.metric_key,
        "metric_label": METRICS[record.metric_key]["label"],
        "metric_unit": METRICS[record.metric_key]["unit"],
        "metric_methodology": METRICS[record.metric_key]["methodology"],
        "review_after_days": record.review_after_days,
        "baseline_period": {
            "start": record.baseline_start.isoformat(),
            "end": record.baseline_end.isoformat(),
        },
        "baseline_value": str(record.baseline_value) if record.baseline_value is not None else None,
        "baseline_available": record.baseline_available,
        "review_period": {
            "start": review_start.isoformat(),
            "end": review_end.isoformat(),
        },
        "observed_value": str(record.observed_value) if record.observed_value is not None else None,
        "change_from_baseline": (
            str(record.observed_value - record.baseline_value)
            if record.observed_value is not None and record.baseline_value is not None
            else None
        ),
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "reviewable": reviewable,
        "status": "Reviewed" if record.reviewed_at else "Ready to review" if reviewable else "Awaiting source data",
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def list_decisions() -> dict[str, Any]:
    available_bounds = _available_bounds()
    with SessionLocal() as session:
        records = session.scalars(
            select(BusinessDecision).order_by(
                BusinessDecision.decision_date.desc(),
                BusinessDecision.id.desc(),
            ).limit(100)
        ).all()
    return {
        "records": [
            _record_payload(record, available_bounds) for record in records
        ],
        "storage": "PostgreSQL",
        "causality_note": "Observed metric changes are descriptive and do not establish that a recorded decision caused them.",
    }


def create_decision(
    *,
    title: str,
    expected_outcome: str,
    decision_date: date,
    metric_key: str,
    review_after_days: int,
) -> dict[str, Any]:
    if metric_key not in METRICS:
        raise ValueError("Unsupported decision metric.")
    baseline_start, baseline_end, _, _ = _decision_periods(
        decision_date, review_after_days
    )
    baseline_value, _ = _metric_value(metric_key, baseline_start, baseline_end)
    with SessionLocal() as session:
        record = BusinessDecision(
            title=title.strip(),
            expected_outcome=expected_outcome.strip(),
            decision_date=decision_date,
            metric_key=metric_key,
            review_after_days=review_after_days,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            baseline_value=baseline_value,
            baseline_available=baseline_value is not None,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        available_bounds = _available_bounds()
        return _record_payload(record, available_bounds)


def review_decision(decision_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        record = session.get(BusinessDecision, decision_id)
        if record is None:
            raise DecisionTrackerNotFound(f"Decision {decision_id} was not found.")
        if record.reviewed_at is not None:
            raise ValueError("This decision has already been reviewed.")
        metric_key = record.metric_key
        _, _, review_start, review_end = _decision_periods(
            record.decision_date, record.review_after_days
        )
        record_id = record.id

    observed_value, unavailable_reason = _metric_value(
        metric_key, review_start, review_end
    )
    if observed_value is None:
        raise ReviewDataUnavailable(
            unavailable_reason or "The selected metric period is not available."
        )

    with SessionLocal() as session:
        record = session.get(BusinessDecision, record_id)
        if record is None:
            raise DecisionTrackerNotFound(f"Decision {record_id} was not found.")
        if record.reviewed_at is not None:
            raise ValueError("This decision has already been reviewed.")
        record.review_start = review_start
        record.review_end = review_end
        record.observed_value = observed_value
        record.reviewed_at = datetime.now(UTC)
        session.commit()
        session.refresh(record)
        available_bounds = _available_bounds()
        payload = _record_payload(record, available_bounds)

    payload["causality_note"] = (
        "This is an observed difference from the recorded baseline. "
        "It does not establish that the decision caused the change."
    )
    return payload
