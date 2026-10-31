import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from biznexa.decision_intelligence import _build_pulse_insights, _calculate_scenario
from biznexa.decision_tracker import ReviewDataUnavailable, _record_payload, _rounded_metric
from biznexa.main import app
from biznexa.models import BusinessDecision
from httpx import ASGITransport, AsyncClient


def request(method, path, json_body=None):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, json=json_body)

    return asyncio.run(send())


def test_pulse_rules_include_evidence_for_cross_functional_signals():
    period = {"start": "2025-01-01", "end": "2025-12-31"}
    comparison_period = {"start": "2024-01-01", "end": "2024-12-31"}
    insights = _build_pulse_insights(
        period=period,
        comparison_period=comparison_period,
        current={
            "gross_sales_usd": "120",
            "gross_profit_usd": "40",
            "order_count": 5,
        },
        comparison={
            "gross_sales_usd": "100",
            "gross_profit_usd": "45",
            "order_count": 4,
        },
        products=[{
            "product_id": "P1",
            "product_name": "Widget",
            "current_revenue_usd": "80",
            "comparison_revenue_usd": "100",
            "current_units_sold": "20",
            "comparison_units_sold": "10",
            "current_inventory_value_usd": "500",
            "comparison_inventory_value_usd": "400",
            "available_qty": 2,
        }],
        inactive_customers=[{
            "customer_id": "C1",
            "customer_name": "Customer One",
        }],
        inactive_customer_count=1,
        suppliers=[{
            "supplier_id": "S1",
            "supplier_name": "Supplier One",
            "late_lines": 2,
            "received_lines": 3,
        }],
    )

    insight_ids = {insight["id"] for insight in insights}
    assert insight_ids == {
        "revenue-up-margin-down",
        "declining-product-stock-up-P1",
        "demand-up-stock-low-P1",
        "high-value-customers-inactive",
        "supplier-late-receipts",
    }
    for insight in insights:
        assert insight["supporting_metric"]["current"]
        assert insight["reporting_period"] == period
        assert insight["comparison_period"] in (None, comparison_period)
        assert insight["methodology"]
        assert insight["explanation"]
        assert insight["next_action"]
        assert insight["limitations"]


def test_pulse_suppresses_temporal_insights_without_comparison_sales():
    insights = _build_pulse_insights(
        period={"start": "2025-01-01", "end": "2025-12-31"},
        comparison_period={"start": "2024-01-01", "end": "2024-12-31"},
        current={"gross_sales_usd": "120", "gross_profit_usd": "40", "order_count": 5},
        comparison={"gross_sales_usd": "0", "gross_profit_usd": "0", "order_count": 0},
        products=[{
            "product_id": "P1",
            "product_name": "Widget",
            "current_revenue_usd": "80",
            "comparison_revenue_usd": "0",
            "current_units_sold": "20",
            "comparison_units_sold": "0",
            "current_inventory_value_usd": "500",
            "comparison_inventory_value_usd": "0",
            "available_qty": 0,
        }],
        inactive_customers=[],
        inactive_customer_count=0,
        suppliers=[],
    )

    assert insights == []


def test_business_pulse_route_returns_the_service_payload(monkeypatch):
    expected = {"insights": [], "comparison_available": False}
    monkeypatch.setattr(
        "biznexa.main.decision_intelligence.business_pulse",
        lambda start, end: expected,
    )

    response = request(
        "GET",
        "/api/analytics/synthetic/business-pulse?start=2025-01-01&end=2025-12-31",
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_business_pulse_route_rejects_invalid_date(monkeypatch):
    monkeypatch.setattr(
        "biznexa.main.decision_intelligence.business_pulse",
        lambda _start, _end: (_ for _ in ()).throw(ValueError("invalid ISO date")),
    )

    response = request(
        "GET",
        "/api/analytics/synthetic/business-pulse?start=not-a-date",
    )

    assert response.status_code == 422


def test_scenario_calculation_uses_documented_baseline_formulas():
    result = _calculate_scenario(
        {
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "gross_sales_usd": "1000",
            "cogs_usd": "600",
            "gross_profit_usd": "400",
            "gross_margin_pct": "40",
            "order_count": 20,
            "customer_count": 10,
            "average_revenue_per_customer_usd": "100",
            "inventory_value_usd": "5000",
            "inventory_snapshot_date": "2025-12-31",
        },
        {
            "sales_growth_pct": Decimal(10),
            "product_cost_change_pct": Decimal(5),
            "retention_change_pct": Decimal(10),
            "inventory_change_pct": Decimal(-20),
            "gross_margin_target_pct": Decimal(50),
        },
    )

    assert result["scenario"] == {
        "projected_revenue_usd": "1200.0000",
        "retention_revenue_change_usd": "100.0000",
        "projected_cogs_usd": "630.0000",
        "projected_gross_profit_usd": "570.0000",
        "projected_gross_margin_pct": "47.5000",
        "projected_inventory_value_usd": "4000.0000",
        "gross_profit_at_target_margin_usd": "600.0000",
        "target_margin_profit_gap_usd": "30.0000",
    }


def test_scenario_with_no_customers_or_inventory_stays_explicit():
    result = _calculate_scenario(
        {
            "period": {"start": "2025-01-01", "end": "2025-01-31"},
            "gross_sales_usd": "0",
            "cogs_usd": "0",
            "gross_profit_usd": "0",
            "gross_margin_pct": None,
            "order_count": 0,
            "customer_count": 0,
            "average_revenue_per_customer_usd": "0",
            "inventory_value_usd": None,
            "inventory_snapshot_date": None,
        },
        {
            "sales_growth_pct": Decimal(10),
            "product_cost_change_pct": Decimal(0),
            "retention_change_pct": Decimal(10),
            "inventory_change_pct": Decimal(5),
            "gross_margin_target_pct": None,
        },
    )

    assert result["scenario"]["projected_revenue_usd"] == "0.0000"
    assert result["scenario"]["projected_gross_margin_pct"] is None
    assert result["scenario"]["projected_inventory_value_usd"] is None
    assert result["scenario"]["gross_profit_at_target_margin_usd"] is None


def test_scenario_route_validates_and_forwards_assumptions(monkeypatch):
    observed = {}

    def scenario(assumptions, start, end):
        observed.update(assumptions=assumptions, start=start, end=end)
        return {"has_sales_data": True}

    monkeypatch.setattr("biznexa.main.decision_intelligence.what_if_scenario", scenario)
    response = request(
        "POST",
        "/api/analytics/synthetic/scenario?start=2025-01-01&end=2025-12-31",
        {},
    )

    assert response.status_code == 200
    assert observed["start"] == "2025-01-01"
    assert observed["end"] == "2025-12-31"
    assert observed["assumptions"]["sales_growth_pct"] == Decimal(0)
    assert observed["assumptions"]["gross_margin_target_pct"] is None


def test_scenario_route_rejects_out_of_range_assumptions():
    response = request(
        "POST",
        "/api/analytics/synthetic/scenario",
        {"sales_growth_pct": 1001},
    )

    assert response.status_code == 422


def test_decision_tracker_list_route_returns_persisted_records(monkeypatch):
    expected = {"records": [], "storage": "PostgreSQL"}
    monkeypatch.setattr("biznexa.main.decision_tracker.list_decisions", lambda: expected)

    response = request("GET", "/api/analytics/synthetic/decision-impact")

    assert response.status_code == 200
    assert response.json() == expected


def test_decision_tracker_create_route_forwards_validated_decision(monkeypatch):
    observed = {}

    def create(**decision):
        observed.update(decision)
        return {"id": 7, **decision}

    monkeypatch.setattr("biznexa.main.decision_tracker.create_decision", create)
    response = request(
        "POST",
        "/api/analytics/synthetic/decision-impact",
        {
            "title": "Review pricing",
            "expected_outcome": "Improve margin",
            "decision_date": "2025-01-01",
            "metric_key": "gross_margin_pct",
            "review_after_days": 45,
        },
    )

    assert response.status_code == 200
    assert observed["decision_date"].isoformat() == "2025-01-01"
    assert observed["metric_key"] == "gross_margin_pct"
    assert observed["review_after_days"] == 45


def test_decision_tracker_create_route_rejects_blank_title():
    response = request(
        "POST",
        "/api/analytics/synthetic/decision-impact",
        {
            "title": "   ",
            "expected_outcome": "Expected change",
            "decision_date": "2025-01-01",
            "metric_key": "gross_sales_usd",
        },
    )

    assert response.status_code == 422


def test_decision_tracker_review_route_reports_unavailable_period(monkeypatch):
    def unavailable(_decision_id):
        raise ReviewDataUnavailable("No receipt lines exist.")

    monkeypatch.setattr("biznexa.main.decision_tracker.review_decision", unavailable)
    response = request(
        "POST",
        "/api/analytics/synthetic/decision-impact/5/review",
        {},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "No receipt lines exist."


def test_decision_tracker_rounds_metrics_and_rehydrates_review_difference():
    record = BusinessDecision(
        id=1,
        title="Pricing review",
        expected_outcome="Margin improves",
        decision_date=date(2025, 1, 1),
        metric_key="gross_margin_pct",
        review_after_days=30,
        baseline_start=date(2024, 12, 2),
        baseline_end=date(2024, 12, 31),
        baseline_value=Decimal("40.1250"),
        baseline_available=True,
        observed_value=Decimal("42.5000"),
        reviewed_at=datetime(2025, 2, 1, tzinfo=UTC),
    )

    payload = _record_payload(
        record,
        {
            "sales": (date(2024, 1, 1), date(2025, 12, 31)),
            "inventory": None,
            "supplier": None,
        },
    )

    assert _rounded_metric(Decimal("1.23456")) == Decimal("1.2346")
    assert payload["change_from_baseline"] == "2.3750"
    assert payload["status"] == "Reviewed"
