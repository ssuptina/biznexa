import asyncio
from decimal import Decimal

import pytest
from biznexa.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError


def request(method, path):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send())


def test_health_does_not_claim_database_connection_when_query_fails(monkeypatch):
    monkeypatch.setattr(
        "biznexa.main.database_health",
        lambda: {"status": "error", "detail": "connection failed"},
    )
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"]["status"] == "error"


def test_database_health_endpoint_returns_service_unavailable_on_failure(monkeypatch):
    monkeypatch.setattr(
        "biznexa.main.database_health",
        lambda: {"status": "error", "detail": "connection failed"},
    )
    response = request("GET", "/health/db")
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "error"


def test_database_health_endpoint_rejects_incomplete_analytics_schema(monkeypatch):
    monkeypatch.setattr(
        "biznexa.main.database_health",
        lambda: {
            "status": "ok",
            "analytics_schema_initialized": False,
            "missing_tables": ["returns"],
            "missing_columns": [],
        },
    )
    response = request("GET", "/health/db")
    assert response.status_code == 503
    assert response.json()["detail"]["missing_tables"] == ["returns"]


def test_health_preserves_actionable_dns_diagnostic(monkeypatch):
    monkeypatch.setattr(
        "biznexa.main.database_health",
        lambda: {
            "status": "error",
            "error_type": "dns",
            "detail": "The PostgreSQL hostname in DATABASE_URL could not be resolved.",
        },
    )
    response = request("GET", "/health")
    assert response.json()["database"]["error_type"] == "dns"


def test_analytics_route_does_not_return_database_exception_details(monkeypatch, caplog):
    def fail(*_args):
        raise SQLAlchemyError("sensitive database diagnostic")

    monkeypatch.setattr("biznexa.main.analytics.overview", fail)
    response = request("GET", "/api/analytics/synthetic/overview")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Analytics query failed. Check database availability and the required schema."
    )
    assert "sensitive database diagnostic" not in response.json()["detail"]
    assert "sensitive database diagnostic" in caplog.text


def test_finance_variance_is_undefined_when_budget_is_zero():
    from biznexa.analytics import _variance_percent

    assert _variance_percent(Decimal(100), Decimal(0)) is None
    assert Decimal(_variance_percent(Decimal(125), Decimal(100))) == 25


def test_supplier_on_time_rate_is_undefined_without_completed_lines():
    from biznexa.analytics import _supplier_on_time_rate_percent

    assert _supplier_on_time_rate_percent(0, 0) is None
    assert Decimal(_supplier_on_time_rate_percent(3, 4)) == 75


def test_schema_guard_rejects_malformed_identifier_before_query(monkeypatch):
    from biznexa import analytics

    monkeypatch.setattr(analytics, "SCHEMA", "public; DROP SCHEMA public")
    with pytest.raises(RuntimeError, match="simple PostgreSQL schema identifier"):
        analytics._schema_guard(object())


def test_supplier_date_filter_preserves_suppliers_without_period_orders(monkeypatch):
    from biznexa import analytics

    class Result:
        def __init__(self, rows=()):
            self.rows = rows

        def scalar_one_or_none(self):
            return "sales_orders"

        def mappings(self):
            return self

        def __iter__(self):
            return iter(self.rows)

    class Connection:
        def __init__(self):
            self.queries = []

        def execute(self, query, _parameters=None):
            sql = str(query)
            self.queries.append(sql)
            if "to_regclass" in sql:
                return Result()
            return Result([{
                "supplier_id": "S-1",
                "supplier_name": "Supplier",
                "quality_rating": Decimal("4.5"),
                "purchase_orders": 0,
                "purchase_value_usd": Decimal(0),
                "received_lines": 0,
                "on_time_lines": 0,
                "late_lines": 0,
                "avg_delay_days": 0,
                "quality_issue_lines": 0,
            }])

    class ConnectionContext:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *_args):
            return False

    class Engine:
        def __init__(self):
            self.connection = Connection()

        def connect(self):
            return ConnectionContext(self.connection)

    engine = Engine()
    monkeypatch.setattr(analytics, "engine", engine)

    result = analytics.suppliers("2024-01-01", "2024-01-31")
    query = " ".join(engine.connection.queries[-1].split())

    expected_join = (
        f"LEFT JOIN {analytics.SCHEMA}.purchase_orders po "
        "ON po.supplier_id = s.supplier_id AND po.order_date BETWEEN"
    )
    assert expected_join in query
    assert "WHERE po.order_date" not in query
    assert result["suppliers"][0]["supplier_id"] == "S-1"
    assert result["suppliers"][0]["on_time_rate_pct"] is None


def test_analytics_schema_contract_reports_missing_tables_and_columns():
    from biznexa.db import _missing_analytics_schema_items

    missing_tables, missing_columns = _missing_analytics_schema_items(
        [("sales_orders", "order_id"), ("sales_orders", "order_date")]
    )
    assert "sales_orders" not in missing_tables
    assert "returns" in missing_tables
    assert missing_columns == ["sales_orders.customer_id", "sales_orders.order_status"]


def test_analytics_schema_contract_requires_purchase_order_date():
    from biznexa.db import _missing_analytics_schema_items

    _, missing_columns = _missing_analytics_schema_items([
        ("purchase_orders", "purchase_order_id"),
        ("purchase_orders", "supplier_id"),
        ("purchase_orders", "promised_delivery_date"),
    ])

    assert missing_columns == ["purchase_orders.order_date"]


def test_analytics_schema_contract_accepts_complete_schema():
    from biznexa.db import _ANALYTICS_SCHEMA_CONTRACT, _missing_analytics_schema_items

    actual_columns = [
        (table, column)
        for table, columns in _ANALYTICS_SCHEMA_CONTRACT.items()
        for column in columns
    ]
    assert _missing_analytics_schema_items(actual_columns) == ([], [])


def test_overview_rejects_unsupported_reporting_granularity():
    response = request(
        "GET",
        "/api/analytics/synthetic/overview?granularity=decade",
    )
    assert response.status_code == 422


def test_sales_rejects_unsupported_reporting_granularity():
    response = request(
        "GET",
        "/api/analytics/synthetic/sales?granularity=decade",
    )
    assert response.status_code == 422


def test_overview_rejects_unsupported_comparison_mode():
    response = request(
        "GET",
        "/api/analytics/synthetic/overview?comparison=invalid",
    )
    assert response.status_code == 422


def test_overview_dashboard_can_omit_daily_series(monkeypatch):
    observed = {}

    def overview(*args):
        observed["args"] = args
        return {"synthetic": True, "daily_sales": []}

    monkeypatch.setattr("biznexa.main.analytics.overview", overview)
    monkeypatch.setattr(
        "biznexa.main.database_health",
        lambda: (_ for _ in ()).throw(AssertionError("health scan should not run per analytics request")),
    )
    response = request(
        "GET",
        "/api/analytics/synthetic/overview?include_daily_sales=false",
    )
    assert response.status_code == 200
    assert observed["args"] == (None, None, "month", "previous_period", False)


def test_overview_keeps_daily_series_enabled_for_existing_clients(monkeypatch):
    observed = {}

    def overview(*args):
        observed["args"] = args
        return {"synthetic": True, "daily_sales": []}

    monkeypatch.setattr("biznexa.main.analytics.overview", overview)
    response = request("GET", "/api/analytics/synthetic/overview")
    assert response.status_code == 200
    assert observed["args"] == (None, None, "month", "previous_period", True)


def test_category_drivers_return_share_and_best_month_for_top_three_categories():
    from biznexa.analytics import _category_drivers

    drivers = _category_drivers(
        [
            {"category": "Electronics", "gross_sales_usd": Decimal("600.00")},
            {"category": "Home", "gross_sales_usd": Decimal("250.00")},
            {"category": "Office", "gross_sales_usd": Decimal("100.00")},
            {"category": "Other", "gross_sales_usd": Decimal("50.00")},
        ],
        [
            {"category": "Electronics", "month": "2024-01-01", "gross_sales_usd": Decimal("250.00")},
            {"category": "Electronics", "month": "2024-02-01", "gross_sales_usd": Decimal("350.00")},
            {"category": "Home", "month": "2024-01-01", "gross_sales_usd": Decimal("125.00")},
            {"category": "Home", "month": "2024-02-01", "gross_sales_usd": Decimal("125.00")},
            {"category": "Office", "month": "2024-02-01", "gross_sales_usd": Decimal("100.00")},
            {"category": "Other", "month": "2024-02-01", "gross_sales_usd": Decimal("50.00")},
        ],
        Decimal("1000.00"),
    )

    assert len(drivers) == 3
    assert drivers[0] == {
        "category": "Electronics",
        "gross_sales_usd": "600.00",
        "contribution_pct": "60.0",
        "best_month": "2024-02-01",
        "best_month_gross_sales_usd": "350.00",
    }
    assert drivers[1]["best_month"] == "2024-01-01"


def test_category_drivers_are_empty_without_gross_sales():
    from biznexa.analytics import _category_drivers

    assert _category_drivers(
        [{"category": "Electronics", "gross_sales_usd": Decimal(0)}],
        [{"category": "Electronics", "month": "2024-01-01", "gross_sales_usd": Decimal(0)}],
        Decimal(0),
    ) == []
