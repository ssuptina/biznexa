"""PostgreSQL-backed customer analytics over the configured imported data schema."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from biznexa.analytics import SCHEMA, _schema_guard
from biznexa.db import engine

_INACTIVITY_DAYS = 90
_MAX_PAGE_SIZE = 100


def _serializable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [
        {key: _serializable(value) for key, value in row.items()}
        for row in result.mappings()
    ]


def _one(result: Any) -> dict[str, Any]:
    row = result.mappings().one()
    return {key: _serializable(value) for key, value in row.items()}


def _period_bounds(
    connection: Any,
    start: str | None,
    end: str | None,
    year: int | None,
    month: int | None,
) -> tuple[date, date, dict[str, str]]:
    if year is not None and not 1900 <= year <= 9999:
        raise ValueError("year must be between 1900 and 9999")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    try:
        requested_start = date.fromisoformat(start) if start else None
        requested_end = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise ValueError("start and end must be valid ISO dates (YYYY-MM-DD)") from exc
    if month is not None and year is None:
        raise ValueError("month requires year")
    if requested_start and requested_end and requested_start > requested_end:
        raise ValueError("start must be on or before end")

    available = _one(connection.execute(text(f"""
        SELECT MIN(o.order_date) AS available_start, MAX(o.order_date) AS available_end
        FROM {SCHEMA}.sales_orders o
        WHERE o.order_status <> 'Cancelled'
          AND EXISTS (
            SELECT 1 FROM {SCHEMA}.sales_order_lines l WHERE l.order_id = o.order_id
          )
    """)))
    if available["available_start"] is None or available["available_end"] is None:
        raise RuntimeError(f"Schema {SCHEMA!r} contains no qualifying customer purchases.")

    available_start = date.fromisoformat(available["available_start"])
    available_end = date.fromisoformat(available["available_end"])

    filter_start: date | None = None
    filter_end: date | None = None
    if year is not None:
        filter_start = date(year, 1, 1)
        filter_end = date(year, 12, 31)
    if month is not None:
        if year is None:
            raise ValueError("month requires year")
        filter_start = date(year, month, 1)
        filter_end = date(year, month, monthrange(year, month)[1])

    starts = [value for value in (requested_start, filter_start) if value is not None]
    ends = [value for value in (requested_end, filter_end) if value is not None]
    period_start = max(starts) if starts else available_start
    period_end = min(ends) if ends else available_end
    period_start = max(period_start, available_start)
    period_end = min(period_end, available_end)
    if period_start > period_end:
        raise ValueError("The selected customer reporting period contains no available dates.")

    return period_start, period_end, {
        "start": available_start.isoformat(),
        "end": available_end.isoformat(),
    }


def _comparison_bounds(start: date, end: date) -> tuple[date, date]:
    comparison_end = start - timedelta(days=1)
    return comparison_end - (end - start), comparison_end


def _base_ctes() -> str:
    return f"""
        WITH line_returns AS (
          SELECT order_line_id,
                 COALESCE(SUM(refund_amount_usd) FILTER (
                   WHERE return_date <= CAST(:end_date AS date)
                 ), 0) AS lifetime_refunds_usd,
                 COALESCE(SUM(refund_amount_usd) FILTER (
                   WHERE return_date BETWEEN CAST(:start_date AS date)
                                         AND CAST(:end_date AS date)
                 ), 0) AS period_refunds_usd,
                 COALESCE(SUM(refund_amount_usd) FILTER (
                   WHERE return_date BETWEEN CAST(:comparison_start AS date)
                                         AND CAST(:comparison_end AS date)
                 ), 0) AS comparison_refunds_usd,
                 COALESCE(SUM(refund_amount_usd) FILTER (
                   WHERE return_date <= CAST(:comparison_end AS date)
                 ), 0) AS comparison_lifetime_refunds_usd
          FROM {SCHEMA}.returns
          GROUP BY order_line_id
        ),
        purchases AS (
          SELECT o.customer_id, o.order_id, o.order_date,
                 SUM(COALESCE(l.line_revenue_usd, 0)) AS gross_sales_usd,
                 SUM(COALESCE(r.lifetime_refunds_usd, 0)) AS lifetime_refunds_usd,
                 SUM(COALESCE(r.period_refunds_usd, 0)) AS period_refunds_usd,
                 SUM(COALESCE(r.comparison_refunds_usd, 0)) AS comparison_refunds_usd,
                 SUM(COALESCE(r.comparison_lifetime_refunds_usd, 0))
                   AS comparison_lifetime_refunds_usd
          FROM {SCHEMA}.sales_orders o
          JOIN {SCHEMA}.sales_order_lines l USING (order_id)
          LEFT JOIN line_returns r USING (order_line_id)
          WHERE o.order_status <> 'Cancelled'
            AND o.order_date <= CAST(:end_date AS date)
          GROUP BY o.customer_id, o.order_id, o.order_date
        ),
        purchase_activity AS (
          SELECT c.customer_id, c.customer_name,
                 MIN(p.order_date) AS first_purchase,
                 MAX(p.order_date) AS last_purchase,
                 COUNT(p.order_id)::integer AS lifetime_order_count,
                 SUM(p.gross_sales_usd) AS lifetime_gross_sales_usd,
                 SUM(p.lifetime_refunds_usd) AS lifetime_refunds_usd,
                 SUM(p.gross_sales_usd - p.lifetime_refunds_usd) AS lifetime_net_sales_usd,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date BETWEEN CAST(:start_date AS date)
                                          AND CAST(:end_date AS date)
                 )::integer AS period_order_count,
                 COALESCE(SUM(p.gross_sales_usd) FILTER (
                   WHERE p.order_date BETWEEN CAST(:start_date AS date)
                                          AND CAST(:end_date AS date)
                 ), 0) AS period_gross_sales_usd,
                 SUM(p.period_refunds_usd) AS period_refunds_usd,
                 MAX(p.order_date) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 ) AS comparison_last_purchase,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 )::integer AS comparison_lifetime_order_count,
                 COALESCE(SUM(
                   p.gross_sales_usd - p.comparison_lifetime_refunds_usd
                 ) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 ), 0) AS comparison_lifetime_net_sales_usd,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date BETWEEN CAST(:comparison_start AS date)
                                          AND CAST(:comparison_end AS date)
                 )::integer AS comparison_order_count,
                 COALESCE(SUM(p.gross_sales_usd) FILTER (
                   WHERE p.order_date BETWEEN CAST(:comparison_start AS date)
                                          AND CAST(:comparison_end AS date)
                 ), 0) AS comparison_gross_sales_usd,
                 SUM(p.comparison_refunds_usd) AS comparison_refunds_usd
          FROM {SCHEMA}.customers c
          JOIN purchases p ON p.customer_id = c.customer_id
          GROUP BY c.customer_id, c.customer_name
        ),
        customer_activity AS (
          SELECT c.customer_id, c.customer_name,
                 a.first_purchase, a.last_purchase,
                 COALESCE(a.lifetime_order_count, 0)::integer AS lifetime_order_count,
                 COALESCE(a.lifetime_gross_sales_usd, 0) AS lifetime_gross_sales_usd,
                 COALESCE(a.lifetime_refunds_usd, 0) AS lifetime_refunds_usd,
                 COALESCE(a.lifetime_net_sales_usd, 0) AS lifetime_net_sales_usd,
                 COALESCE(a.period_order_count, 0)::integer AS period_order_count,
                 COALESCE(a.period_gross_sales_usd, 0) AS period_gross_sales_usd,
                 COALESCE(a.period_refunds_usd, 0) AS period_refunds_usd,
                 a.comparison_last_purchase,
                 COALESCE(a.comparison_lifetime_order_count, 0)::integer
                   AS comparison_lifetime_order_count,
                 COALESCE(a.comparison_lifetime_net_sales_usd, 0)
                   AS comparison_lifetime_net_sales_usd,
                 COALESCE(a.comparison_order_count, 0)::integer AS comparison_order_count,
                 COALESCE(a.comparison_gross_sales_usd, 0) AS comparison_gross_sales_usd,
                 COALESCE(a.comparison_refunds_usd, 0) AS comparison_refunds_usd
          FROM {SCHEMA}.customers c
          LEFT JOIN purchase_activity a USING (customer_id)
        )
    """


def _query_parameters(
    start: date,
    end: date,
    comparison_start: date,
    comparison_end: date,
) -> dict[str, str]:
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "comparison_start": comparison_start.isoformat(),
        "comparison_end": comparison_end.isoformat(),
    }


def _cohort_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cohorts_by_month: dict[str, dict[str, Any]] = {}
    for row in rows:
        cohort_month = row["cohort_month"][:7]
        cohort = cohorts_by_month.setdefault(cohort_month, {
            "cohort_month": cohort_month,
            "cohort_size": row["cohort_size"],
            "retention": [],
        })
        retained = int(row["retained_customers"])
        cohort["retention"].append({
            "month_number": int(row["month_number"]),
            "retained_customers": retained,
            "retention_pct": round(retained / int(row["cohort_size"]) * 100, 1)
                if row["cohort_size"] else 0,
        })
    return list(cohorts_by_month.values())


def _rfm_ctes() -> str:
    return """
        WITH rfm_scores AS (
          SELECT customer_id,
                 NTILE(5) OVER (ORDER BY last_purchase ASC, customer_id) AS recency_score,
                 NTILE(5) OVER (ORDER BY lifetime_order_count ASC, customer_id)
                   AS frequency_score,
                 NTILE(5) OVER (ORDER BY lifetime_net_sales_usd ASC, customer_id)
                   AS monetary_score
          FROM pg_temp.biznexa_customer_activity
          WHERE lifetime_order_count > 0
        ),
        classified AS (
          SELECT a.*,
                 s.recency_score, s.frequency_score, s.monetary_score,
                 CASE
                   WHEN a.lifetime_order_count = 0 THEN 'Unscored - no purchase history'
                   WHEN s.recency_score >= 4 AND s.frequency_score >= 4
                        AND s.monetary_score >= 4 THEN 'Champions'
                   WHEN s.recency_score >= 3 AND s.frequency_score >= 4
                     THEN 'Loyal customers'
                   WHEN a.lifetime_order_count = 1
                        AND a.first_purchase >= CAST(:end_date AS date) - 30
                     THEN 'New customers'
                   WHEN s.recency_score >= 4 AND s.frequency_score >= 2
                     THEN 'Potential loyalists'
                   WHEN s.recency_score <= 2 AND s.frequency_score >= 3
                     THEN 'At-risk customers'
                   WHEN s.recency_score <= 2 THEN 'Customers needing attention'
                   ELSE 'Hibernating customers'
                 END AS rfm_segment,
                 CASE WHEN a.last_purchase >= CAST(:cutoff AS date)
                      THEN 'active' ELSE 'inactive' END AS activity_status,
                 CASE
                   WHEN a.period_order_count = 0 THEN 'No purchase in selected period'
                   WHEN a.first_purchase BETWEEN CAST(:start_date AS date)
                                             AND CAST(:end_date AS date) THEN 'New'
                   ELSE 'Returning'
                 END AS customer_segment,
                 CASE WHEN a.last_purchase IS NOT NULL
                      THEN CAST(CAST(:end_date AS date) - a.last_purchase AS integer)
                      ELSE NULL
                 END AS days_since_last_purchase,
                 a.period_gross_sales_usd - a.period_refunds_usd AS period_net_sales_usd
          FROM pg_temp.biznexa_customer_activity a
          LEFT JOIN rfm_scores s USING (customer_id)
        )
    """


def _materialize_customer_data(connection: Any, parameters: dict[str, Any]) -> None:
    connection.execute(
        text(
            "CREATE TEMP TABLE biznexa_customer_purchases ON COMMIT DROP AS "
            + _base_ctes()
            + " SELECT * FROM purchases"
        ),
        parameters,
    )
    connection.execute(text(f"""
        CREATE TEMP TABLE biznexa_customer_activity ON COMMIT DROP AS
        WITH purchase_activity AS (
          SELECT c.customer_id, c.customer_name,
                 MIN(p.order_date) AS first_purchase,
                 MAX(p.order_date) AS last_purchase,
                 COUNT(p.order_id)::integer AS lifetime_order_count,
                 SUM(p.gross_sales_usd) AS lifetime_gross_sales_usd,
                 SUM(p.lifetime_refunds_usd) AS lifetime_refunds_usd,
                 SUM(p.gross_sales_usd - p.lifetime_refunds_usd) AS lifetime_net_sales_usd,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date BETWEEN CAST(:start_date AS date)
                                          AND CAST(:end_date AS date)
                 )::integer AS period_order_count,
                 COALESCE(SUM(p.gross_sales_usd) FILTER (
                   WHERE p.order_date BETWEEN CAST(:start_date AS date)
                                          AND CAST(:end_date AS date)
                 ), 0) AS period_gross_sales_usd,
                 SUM(p.period_refunds_usd) AS period_refunds_usd,
                 MAX(p.order_date) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 ) AS comparison_last_purchase,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 )::integer AS comparison_lifetime_order_count,
                 COALESCE(SUM(
                   p.gross_sales_usd - p.comparison_lifetime_refunds_usd
                 ) FILTER (
                   WHERE p.order_date <= CAST(:comparison_end AS date)
                 ), 0) AS comparison_lifetime_net_sales_usd,
                 COUNT(p.order_id) FILTER (
                   WHERE p.order_date BETWEEN CAST(:comparison_start AS date)
                                          AND CAST(:comparison_end AS date)
                 )::integer AS comparison_order_count,
                 COALESCE(SUM(p.gross_sales_usd) FILTER (
                   WHERE p.order_date BETWEEN CAST(:comparison_start AS date)
                                          AND CAST(:comparison_end AS date)
                 ), 0) AS comparison_gross_sales_usd,
                 SUM(p.comparison_refunds_usd) AS comparison_refunds_usd
          FROM pg_temp.biznexa_customer_purchases p
          JOIN {SCHEMA}.customers c USING (customer_id)
          GROUP BY c.customer_id, c.customer_name
        ),
        customer_activity AS (
          SELECT c.customer_id, c.customer_name,
                 a.first_purchase, a.last_purchase,
                 COALESCE(a.lifetime_order_count, 0)::integer AS lifetime_order_count,
                 COALESCE(a.lifetime_gross_sales_usd, 0) AS lifetime_gross_sales_usd,
                 COALESCE(a.lifetime_refunds_usd, 0) AS lifetime_refunds_usd,
                 COALESCE(a.lifetime_net_sales_usd, 0) AS lifetime_net_sales_usd,
                 COALESCE(a.period_order_count, 0)::integer AS period_order_count,
                 COALESCE(a.period_gross_sales_usd, 0) AS period_gross_sales_usd,
                 COALESCE(a.period_refunds_usd, 0) AS period_refunds_usd,
                 a.comparison_last_purchase,
                 COALESCE(a.comparison_lifetime_order_count, 0)::integer
                   AS comparison_lifetime_order_count,
                 COALESCE(a.comparison_lifetime_net_sales_usd, 0)
                   AS comparison_lifetime_net_sales_usd,
                 COALESCE(a.comparison_order_count, 0)::integer AS comparison_order_count,
                 COALESCE(a.comparison_gross_sales_usd, 0) AS comparison_gross_sales_usd,
                 COALESCE(a.comparison_refunds_usd, 0) AS comparison_refunds_usd
          FROM {SCHEMA}.customers c
          LEFT JOIN purchase_activity a USING (customer_id)
        )
        SELECT * FROM customer_activity
    """), parameters)
    connection.execute(text("""
        CREATE TEMP TABLE biznexa_customer_classified ON COMMIT DROP AS
    """ + _rfm_ctes() + " SELECT * FROM classified"), parameters)


def customers(
    start: str | None = None,
    end: str | None = None,
    year: int | None = None,
    month: int | None = None,
    search: str | None = None,
    segment: str | None = None,
    activity_status: str | None = None,
    rfm_segment: str | None = None,
    min_revenue: Decimal | None = None,
    max_revenue: Decimal | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= page_size <= _MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {_MAX_PAGE_SIZE}")
    if min_revenue is not None and max_revenue is not None and min_revenue > max_revenue:
        raise ValueError("min_revenue must be less than or equal to max_revenue")
    if activity_status not in (None, "active", "inactive"):
        raise ValueError("activity_status must be active or inactive")
    if segment not in (None, "New", "Returning", "No purchase in selected period"):
        raise ValueError("segment must be New, Returning, or No purchase in selected period")
    if rfm_segment not in (
        None, "Champions", "Loyal customers", "Potential loyalists", "New customers",
        "At-risk customers", "Customers needing attention", "Hibernating customers",
        "Unscored - no purchase history",
    ):
        raise ValueError("rfm_segment is not a supported customer classification")

    with engine.connect() as connection:
        _schema_guard(connection)
        period_start, period_end, available_period = _period_bounds(
            connection, start, end, year, month
        )
        comparison_start, comparison_end = _comparison_bounds(period_start, period_end)
        parameters = _query_parameters(
            period_start, period_end, comparison_start, comparison_end
        )
        parameters["cutoff"] = (period_end - timedelta(days=_INACTIVITY_DAYS)).isoformat()
        parameters["search"] = f"%{search.strip()}%" if search and search.strip() else None
        parameters["segment"] = segment
        parameters["activity_status"] = activity_status
        parameters["rfm_segment"] = rfm_segment
        parameters["min_revenue"] = min_revenue
        parameters["max_revenue"] = max_revenue
        parameters["page_size"] = page_size
        parameters["offset"] = (page - 1) * page_size
        parameters["inactivity_days"] = _INACTIVITY_DAYS

        _materialize_customer_data(connection, parameters)

        summary = _one(connection.execute(text("""
            SELECT COUNT(DISTINCT customer_id)::integer AS known_customers,
                   COUNT(*) FILTER (WHERE lifetime_order_count > 0)::integer
                     AS purchasing_customers,
                   COUNT(*) FILTER (WHERE period_order_count > 0)::integer AS period_customers,
                   COUNT(*) FILTER (WHERE last_purchase >= CAST(:cutoff AS date))::integer
                     AS active_customers,
                   COUNT(*) FILTER (
                     WHERE last_purchase < CAST(:cutoff AS date) OR last_purchase IS NULL
                   )::integer
                     AS inactive_customers,
                   COUNT(*) FILTER (
                     WHERE comparison_last_purchase >=
                           CAST(:comparison_end AS date) - :inactivity_days
                   )::integer AS comparison_active_customers,
                   COUNT(*) FILTER (
                     WHERE comparison_last_purchase IS NULL
                        OR comparison_last_purchase <
                           CAST(:comparison_end AS date) - :inactivity_days
                   )::integer AS comparison_inactive_customers,
                   COUNT(*) FILTER (
                     WHERE period_order_count > 0 AND lifetime_order_count >= 2
                   )::integer AS repeat_customers,
                   COUNT(*) FILTER (
                     WHERE first_purchase BETWEEN CAST(:start_date AS date)
                                              AND CAST(:end_date AS date)
                   )::integer AS new_customers,
                   COUNT(*) FILTER (WHERE lifetime_order_count = 1)::integer AS one_time_customers,
                   COUNT(*) FILTER (
                     WHERE comparison_lifetime_order_count = 1
                   )::integer AS comparison_one_time_customers,
                   COALESCE(AVG(lifetime_net_sales_usd) FILTER (
                     WHERE lifetime_order_count > 0
                   ), 0)
                     AS average_customer_lifetime_value_usd,
                   COALESCE(AVG(comparison_lifetime_net_sales_usd) FILTER (
                     WHERE comparison_lifetime_order_count > 0
                   ), 0) AS comparison_average_customer_lifetime_value_usd,
                   COALESCE(
                     SUM(period_order_count)::numeric
                       / NULLIF(COUNT(*) FILTER (WHERE period_order_count > 0), 0),
                     0
                   ) AS average_purchase_frequency,
                   COALESCE(
                     SUM(period_gross_sales_usd - period_refunds_usd)
                       / NULLIF(SUM(period_order_count), 0),
                     0
                   ) AS average_order_value_usd,
                   COALESCE(
                     SUM(comparison_gross_sales_usd - comparison_refunds_usd)
                       / NULLIF(SUM(comparison_order_count), 0),
                     0
                   ) AS comparison_average_order_value_usd,
                   COUNT(*) FILTER (WHERE comparison_order_count > 0)::integer
                     AS comparison_customers,
                   COUNT(*) FILTER (
                     WHERE comparison_order_count > 0
                       AND comparison_lifetime_order_count >= 2
                   )::integer AS comparison_repeat_customers,
                   COUNT(*) FILTER (
                     WHERE first_purchase BETWEEN CAST(:comparison_start AS date)
                                              AND CAST(:comparison_end AS date)
                   )::integer AS comparison_new_customers,
                   COALESCE(
                     SUM(comparison_order_count)::numeric
                       / NULLIF(COUNT(*) FILTER (WHERE comparison_order_count > 0), 0),
                     0
                   ) AS comparison_average_purchase_frequency
            FROM pg_temp.biznexa_customer_activity
        """), parameters))

        def percent_change(current: Any, previous: Any) -> str | None:
            previous_value = Decimal(str(previous))
            if previous_value == 0:
                return None
            return str(
                (Decimal(str(current)) - previous_value) / previous_value
                * Decimal(100)
            )

        comparison_metrics = []
        for key, current_key, previous_key in (
            ("active_customers", "active_customers", "comparison_active_customers"),
            ("inactive_customers", "inactive_customers", "comparison_inactive_customers"),
            ("period_customers", "period_customers", "comparison_customers"),
            ("repeat_customers", "repeat_customers", "comparison_repeat_customers"),
            ("new_customers", "new_customers", "comparison_new_customers"),
            ("one_time_customers", "one_time_customers", "comparison_one_time_customers"),
            (
                "average_customer_lifetime_value_usd",
                "average_customer_lifetime_value_usd",
                "comparison_average_customer_lifetime_value_usd",
            ),
            (
                "average_purchase_frequency",
                "average_purchase_frequency",
                "comparison_average_purchase_frequency",
            ),
            (
                "average_order_value_usd",
                "average_order_value_usd",
                "comparison_average_order_value_usd",
            ),
        ):
            comparison_metrics.append({
                "metric": key,
                "current": summary[current_key],
                "previous": summary[previous_key],
                "change_pct": percent_change(summary[current_key], summary[previous_key]),
            })

        segment_rows = _rows(connection.execute(text("""
            SELECT CASE
                     WHEN period_order_count = 0 THEN 'No purchase in selected period'
                     WHEN first_purchase BETWEEN CAST(:start_date AS date)
                                            AND CAST(:end_date AS date) THEN 'New'
                     ELSE 'Returning'
                   END AS segment,
                   COUNT(DISTINCT customer_id)::integer AS customers,
                   COALESCE(SUM(period_gross_sales_usd - period_refunds_usd), 0)
                     AS period_net_sales_usd,
                   COALESCE(
                     SUM(period_gross_sales_usd - period_refunds_usd)
                       / NULLIF(SUM(period_order_count), 0),
                     0
                   ) AS average_order_value_usd
            FROM pg_temp.biznexa_customer_activity
            GROUP BY 1
            ORDER BY 1
        """), parameters))

        monthly_rows = _rows(connection.execute(text(f"""
            WITH first_purchase AS (
              SELECT customer_id, MIN(order_date) AS first_purchase_date,
                     date_trunc('month', MIN(order_date))::date AS cohort_month
              FROM pg_temp.biznexa_customer_purchases
              GROUP BY customer_id
            ),
            monthly_activity AS (
              SELECT customer_id, date_trunc('month', order_date)::date AS purchase_month,
                     SUM(gross_sales_usd) AS gross_sales_usd
              FROM pg_temp.biznexa_customer_purchases
              WHERE order_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
              GROUP BY customer_id, date_trunc('month', order_date)::date
            ),
            monthly_refunds AS (
              SELECT o.customer_id,
                     date_trunc('month', r.return_date)::date AS return_month,
                     SUM(COALESCE(r.refund_amount_usd, 0)) AS refunds_usd
              FROM {SCHEMA}.returns r
              JOIN {SCHEMA}.sales_order_lines l USING (order_line_id)
              JOIN {SCHEMA}.sales_orders o USING (order_id)
              WHERE o.order_status <> 'Cancelled'
                AND o.order_date <= CAST(:end_date AS date)
                AND r.return_date BETWEEN CAST(:start_date AS date)
                                      AND CAST(:end_date AS date)
              GROUP BY o.customer_id, date_trunc('month', r.return_date)::date
            ),
            monthly_totals AS (
              SELECT customer_id, purchase_month AS month, gross_sales_usd,
                     0::numeric AS refunds_usd, TRUE AS has_purchase
              FROM monthly_activity
              UNION ALL
              SELECT customer_id, return_month AS month, 0::numeric AS gross_sales_usd,
                     refunds_usd, FALSE AS has_purchase
              FROM monthly_refunds
            ),
            selected_months AS (
              SELECT generate_series(
                date_trunc('month', CAST(:start_date AS date))::date,
                date_trunc('month', CAST(:end_date AS date))::date,
                interval '1 month'
              )::date AS month
            )
            SELECT m.month,
                   COUNT(DISTINCT t.customer_id) FILTER (
                     WHERE t.has_purchase
                   )::integer AS active_customers,
                   COUNT(DISTINCT t.customer_id) FILTER (
                     WHERE t.has_purchase
                       AND f.first_purchase_date BETWEEN CAST(:start_date AS date)
                                                      AND CAST(:end_date AS date)
                       AND f.cohort_month = m.month
                   )::integer AS new_customers,
                   COUNT(DISTINCT t.customer_id) FILTER (
                     WHERE t.has_purchase
                       AND (
                         f.first_purchase_date < CAST(:start_date AS date)
                         OR f.cohort_month < m.month
                       )
                   )::integer AS returning_customers,
                   COALESCE(SUM(t.gross_sales_usd - t.refunds_usd), 0) AS net_sales_usd
            FROM selected_months m
            LEFT JOIN monthly_totals t ON t.month = m.month
            LEFT JOIN first_purchase f ON f.customer_id = t.customer_id
            GROUP BY m.month
            ORDER BY m.month
        """), parameters))

        cohort_rows = _rows(connection.execute(text("""
            WITH first_purchase AS (
              SELECT customer_id, MIN(order_date) AS first_purchase,
                     date_trunc('month', MIN(order_date))::date AS cohort_month
              FROM pg_temp.biznexa_customer_purchases
              GROUP BY customer_id
            ),
            cohort_sizes AS (
              SELECT cohort_month, COUNT(*)::integer AS cohort_size
              FROM first_purchase
              WHERE first_purchase BETWEEN CAST(:start_date AS date)
                                       AND CAST(:end_date AS date)
              GROUP BY cohort_month
            ),
            monthly_activity AS (
              SELECT DISTINCT customer_id, date_trunc('month', order_date)::date AS purchase_month
              FROM pg_temp.biznexa_customer_purchases
            ),
            cohort_months AS (
              SELECT s.cohort_month, s.cohort_size, gs.month_number,
                     (s.cohort_month + gs.month_number * interval '1 month')::date
                       AS activity_month
              FROM cohort_sizes s
              CROSS JOIN LATERAL generate_series(
                0,
                LEAST(
                  11,
                  (EXTRACT(YEAR FROM age(date_trunc('month', CAST(:end_date AS date)),
                                           s.cohort_month))::integer * 12)
                    + EXTRACT(MONTH FROM age(date_trunc('month', CAST(:end_date AS date)),
                                             s.cohort_month))::integer
                )
              ) AS gs(month_number)
            )
            SELECT cm.cohort_month, cm.month_number, cm.cohort_size,
                   COUNT(DISTINCT a.customer_id)::integer AS retained_customers
            FROM cohort_months cm
            LEFT JOIN first_purchase f
              ON f.cohort_month = cm.cohort_month
             AND f.first_purchase BETWEEN CAST(:start_date AS date)
                                      AND CAST(:end_date AS date)
            LEFT JOIN monthly_activity a
              ON a.customer_id = f.customer_id AND a.purchase_month = cm.activity_month
            GROUP BY cm.cohort_month, cm.month_number, cm.cohort_size
            ORDER BY cm.cohort_month, cm.month_number
        """), parameters))

        frequency_rows = _rows(connection.execute(text("""
            SELECT CASE
                     WHEN lifetime_order_count = 1 THEN '1'
                     WHEN lifetime_order_count = 2 THEN '2'
                     WHEN lifetime_order_count BETWEEN 3 AND 5 THEN '3–5'
                     ELSE '6+'
                   END AS order_frequency,
                   COUNT(*)::integer AS customers
            FROM pg_temp.biznexa_customer_activity
            WHERE lifetime_order_count > 0
            GROUP BY 1
            ORDER BY MIN(lifetime_order_count)
        """), parameters))

        value_rows = _rows(connection.execute(text("""
            WITH ranked_values AS (
              SELECT lifetime_net_sales_usd,
                     NTILE(5) OVER (ORDER BY lifetime_net_sales_usd) AS value_quintile
              FROM pg_temp.biznexa_customer_activity
              WHERE lifetime_order_count > 0
            )
            SELECT value_quintile, COUNT(*)::integer AS customers,
                   MIN(lifetime_net_sales_usd) AS minimum_net_sales_usd,
                   MAX(lifetime_net_sales_usd) AS maximum_net_sales_usd
            FROM ranked_values
            GROUP BY value_quintile
            ORDER BY value_quintile
        """), parameters))

        filtered_customers = _rows(connection.execute(text("""
            SELECT customer_id, customer_name, first_purchase, last_purchase,
                   lifetime_order_count AS total_orders,
                   lifetime_net_sales_usd AS lifetime_net_sales_usd,
                   period_order_count, period_net_sales_usd,
                   CASE WHEN lifetime_order_count > 0
                        THEN lifetime_net_sales_usd / lifetime_order_count ELSE 0 END
                     AS average_order_value_usd,
                   days_since_last_purchase, customer_segment, activity_status,
                   recency_score, frequency_score, monetary_score, rfm_segment
            FROM pg_temp.biznexa_customer_classified
            WHERE (CAST(:search AS text) IS NULL
                   OR CAST(customer_id AS text) ILIKE CAST(:search AS text)
                   OR COALESCE(customer_name, '') ILIKE :search)
              AND (CAST(:segment AS text) IS NULL
                   OR customer_segment = CAST(:segment AS text))
              AND (CAST(:activity_status AS text) IS NULL
                   OR activity_status = CAST(:activity_status AS text))
              AND (CAST(:rfm_segment AS text) IS NULL
                   OR rfm_segment = CAST(:rfm_segment AS text))
              AND (CAST(:min_revenue AS numeric) IS NULL
                   OR lifetime_net_sales_usd >= CAST(:min_revenue AS numeric))
              AND (CAST(:max_revenue AS numeric) IS NULL
                   OR lifetime_net_sales_usd <= CAST(:max_revenue AS numeric))
            ORDER BY lifetime_net_sales_usd DESC, customer_id
            LIMIT :page_size OFFSET :offset
        """), parameters))

        count_row = _one(connection.execute(text("""
            SELECT COUNT(*)::integer AS total
            FROM pg_temp.biznexa_customer_classified
            WHERE (CAST(:search AS text) IS NULL
                   OR CAST(customer_id AS text) ILIKE CAST(:search AS text)
                   OR COALESCE(customer_name, '') ILIKE :search)
              AND (CAST(:segment AS text) IS NULL
                   OR customer_segment = CAST(:segment AS text))
              AND (CAST(:activity_status AS text) IS NULL
                   OR activity_status = CAST(:activity_status AS text))
              AND (CAST(:rfm_segment AS text) IS NULL
                   OR rfm_segment = CAST(:rfm_segment AS text))
              AND (CAST(:min_revenue AS numeric) IS NULL
                   OR lifetime_net_sales_usd >= CAST(:min_revenue AS numeric))
              AND (CAST(:max_revenue AS numeric) IS NULL
                   OR lifetime_net_sales_usd <= CAST(:max_revenue AS numeric))
        """), parameters))

        rfm_rows = _rows(connection.execute(text("""
            SELECT rfm_segment, COUNT(DISTINCT customer_id)::integer AS customers
            FROM pg_temp.biznexa_customer_classified
            WHERE lifetime_order_count > 0
            GROUP BY rfm_segment
            ORDER BY customers DESC, rfm_segment
        """), parameters))

    segments = [
        {
            "segment": row["segment"],
            "customers": row["customers"],
            "period_net_sales_usd": row["period_net_sales_usd"],
            "average_order_value_usd": row["average_order_value_usd"],
        }
        for row in segment_rows
    ]
    return {
        "synthetic": True,
        "as_of": period_end.isoformat(),
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "available_period": available_period,
        "inactivity_days": _INACTIVITY_DAYS,
        "definitions": {
            "qualifying_purchase": "A non-cancelled order with at least one sales-order line.",
            "total_customers": "Distinct customer-directory IDs, including customers with no qualifying purchase history.",
            "purchasing_customers": "Distinct directory customers with qualifying purchase history through the selected period end.",
            "period_customers": "Distinct customers with a qualifying purchase inside the selected inclusive reporting period; this matches the Executive Overview distinct line-backed customer count for the same dates.",
            "net_sales": "Line revenue less recorded refunds dated within the selected period; monthly trend refunds are attributed to their return month.",
            "inactive": f"No qualifying purchase in the {_INACTIVITY_DAYS} days before the selected period end, including customers with no purchase history. This is observed inactivity, not predicted churn.",
            "average_purchase_frequency": "Qualifying orders in the selected period divided by distinct customers purchasing in that period.",
            "average_order_value": "Customer table values are historical lifetime net sales divided by lifetime qualifying orders; segment AOV uses selected-period net sales divided by selected-period orders.",
            "rfm": "Heuristic quintile scoring as of period end for purchasers only. Recency 5 is most recent; Frequency and Monetary 5 are highest. No-purchase customers are unscored. Rules are ordered and mutually exclusive; these are not predictions.",
            "cohort_retention": "Acquisition month is each customer's first qualifying purchase month. A customer is retained in a later month only when they have at least one qualifying order in that month.",
        },
        "summary": summary,
        "comparison": {
            "start": comparison_start.isoformat(),
            "end": comparison_end.isoformat(),
            "metrics": comparison_metrics,
        },
        "segments": segments,
        "monthly_trend": monthly_rows,
        "cohorts": _cohort_payload(cohort_rows),
        "purchase_frequency_distribution": frequency_rows,
        "customer_value_distribution": value_rows,
        "rfm_segments": rfm_rows,
        "customers": filtered_customers,
        "pagination": {"page": page, "page_size": page_size, "total": count_row["total"]},
    }


def customer_detail(customer_id: str, as_of: str | None = None) -> dict[str, Any]:
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as exc:
        raise ValueError("as_of must be a valid ISO date (YYYY-MM-DD)") from exc

    with engine.connect() as connection:
        _schema_guard(connection)
        if as_of_date is None:
            result = connection.execute(text(f"""
                SELECT MAX(o.order_date) AS as_of
                FROM {SCHEMA}.sales_orders o
                JOIN {SCHEMA}.sales_order_lines l USING (order_id)
                WHERE o.order_status <> 'Cancelled'
            """)).scalar_one_or_none()
            if result is None:
                raise RuntimeError("No qualifying customer purchases are available.")
            as_of_date = result

        parameters = {"customer_id": customer_id, "as_of": as_of_date.isoformat()}
        customer = connection.execute(text(f"""
            WITH line_returns AS (
              SELECT order_line_id, SUM(refund_amount_usd) AS refunds_usd
              FROM {SCHEMA}.returns
              WHERE return_date <= CAST(:as_of AS date)
              GROUP BY order_line_id
            ),
            purchase_summary AS (
              SELECT o.customer_id,
                     MIN(o.order_date) AS first_purchase,
                     MAX(o.order_date) AS last_purchase,
                     COUNT(DISTINCT o.order_id)::integer AS total_orders,
                     COALESCE(SUM(COALESCE(l.line_revenue_usd, 0)), 0) AS gross_sales_usd,
                     COALESCE(SUM(COALESCE(r.refunds_usd, 0)), 0) AS refunds_usd
              FROM {SCHEMA}.sales_orders o
              JOIN {SCHEMA}.sales_order_lines l USING (order_id)
              LEFT JOIN line_returns r USING (order_line_id)
              WHERE o.order_status <> 'Cancelled' AND o.order_date <= CAST(:as_of AS date)
              GROUP BY o.customer_id
            )
            SELECT c.customer_id, c.customer_name,
                   p.first_purchase, p.last_purchase,
                   COALESCE(p.total_orders, 0)::integer AS total_orders,
                   COALESCE(p.gross_sales_usd, 0) AS gross_sales_usd,
                   COALESCE(p.refunds_usd, 0) AS refunds_usd
            FROM {SCHEMA}.customers c
            LEFT JOIN purchase_summary p USING (customer_id)
            WHERE CAST(c.customer_id AS text) = :customer_id
        """), parameters).mappings().one_or_none()
        if customer is None:
            raise ValueError("Customer ID was not found in the customer directory.")

        purchase_history = _rows(connection.execute(text(f"""
            WITH line_returns AS (
              SELECT order_line_id, SUM(refund_amount_usd) AS refunds_usd
              FROM {SCHEMA}.returns
              WHERE return_date <= CAST(:as_of AS date)
              GROUP BY order_line_id
            )
            SELECT o.order_id, o.order_date,
                   SUM(COALESCE(l.line_revenue_usd, 0)) AS gross_sales_usd,
                   SUM(COALESCE(r.refunds_usd, 0)) AS refunds_usd,
                   SUM(COALESCE(l.line_revenue_usd, 0) - COALESCE(r.refunds_usd, 0))
                     AS net_sales_usd,
                   COUNT(DISTINCT l.product_id)::integer AS product_count
            FROM {SCHEMA}.sales_orders o
            JOIN {SCHEMA}.sales_order_lines l USING (order_id)
            LEFT JOIN line_returns r USING (order_line_id)
            WHERE CAST(o.customer_id AS text) = :customer_id
              AND o.order_status <> 'Cancelled' AND o.order_date <= CAST(:as_of AS date)
            GROUP BY o.order_id, o.order_date
            ORDER BY o.order_date DESC, o.order_id DESC
            LIMIT 36
        """), parameters))
        product_preferences = _rows(connection.execute(text(f"""
            SELECT p.product_id, p.product_name, p.category,
                   COUNT(DISTINCT o.order_id)::integer AS order_count,
                   SUM(COALESCE(l.line_revenue_usd, 0)) AS gross_sales_usd
            FROM {SCHEMA}.sales_orders o
            JOIN {SCHEMA}.sales_order_lines l USING (order_id)
            JOIN {SCHEMA}.products p USING (product_id)
            WHERE CAST(o.customer_id AS text) = :customer_id
              AND o.order_status <> 'Cancelled' AND o.order_date <= CAST(:as_of AS date)
            GROUP BY p.product_id, p.product_name, p.category
            ORDER BY gross_sales_usd DESC, p.product_id
            LIMIT 5
        """), parameters))

    record = {key: _serializable(value) for key, value in customer.items()}
    record["net_sales_usd"] = str(
        Decimal(str(record["gross_sales_usd"])) - Decimal(str(record["refunds_usd"]))
    )
    record["days_since_last_purchase"] = (
        (as_of_date - date.fromisoformat(record["last_purchase"])).days
        if record["last_purchase"] else None
    )
    record["inactivity_status"] = (
        "inactive"
        if record["days_since_last_purchase"] is None
        or record["days_since_last_purchase"] > _INACTIVITY_DAYS
        else "active"
    )
    return {
        "customer": record,
        "as_of": as_of_date.isoformat(),
        "inactivity_days": _INACTIVITY_DAYS,
        "purchase_history": purchase_history,
        "product_preferences": product_preferences,
    }
