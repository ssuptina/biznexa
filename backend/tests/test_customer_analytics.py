import asyncio
from datetime import date

import pytest
from biznexa import customer_analytics
from biznexa.main import app
from httpx import ASGITransport, AsyncClient


def request(method, path):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send())


class _Connection:
    def execute(self, *_args, **_kwargs):
        return object()


def test_period_bounds_resolve_inclusive_month_filter(monkeypatch):
    monkeypatch.setattr(
        customer_analytics,
        "_one",
        lambda _result: {
            "available_start": "2023-02-01",
            "available_end": "2025-11-30",
        },
    )

    start, end, available = customer_analytics._period_bounds(
        _Connection(), None, None, 2024, 2
    )

    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 29)
    assert available == {"start": "2023-02-01", "end": "2025-11-30"}


def test_period_bounds_intersect_global_date_range_and_year_filter(monkeypatch):
    monkeypatch.setattr(
        customer_analytics,
        "_one",
        lambda _result: {
            "available_start": "2023-01-01",
            "available_end": "2025-12-31",
        },
    )

    start, end, _ = customer_analytics._period_bounds(
        _Connection(), "2024-03-10", "2024-09-10", 2024, None
    )

    assert start == date(2024, 3, 10)
    assert end == date(2024, 9, 10)


@pytest.mark.parametrize(
    ("start", "end", "year", "month", "message"),
    [
        ("2024-10-01", "2024-09-30", None, None, "start must be on or before end"),
        (None, None, None, 2, "month requires year"),
        (None, None, 2024, 13, "month must be between 1 and 12"),
    ],
)
def test_period_bounds_reject_invalid_filters(start, end, year, month, message):
    with pytest.raises(ValueError, match=message):
        customer_analytics._period_bounds(
            _Connection(), start, end, year, month
        )


def test_cohort_payload_uses_retained_counts_and_rates():
    result = customer_analytics._cohort_payload([
        {
            "cohort_month": "2024-01-01",
            "cohort_size": 2,
            "month_number": 0,
            "retained_customers": 2,
        },
        {
            "cohort_month": "2024-01-01",
            "cohort_size": 2,
            "month_number": 1,
            "retained_customers": 1,
        },
    ])

    assert result == [{
        "cohort_month": "2024-01",
        "cohort_size": 2,
        "retention": [
            {"month_number": 0, "retained_customers": 2, "retention_pct": 100.0},
            {"month_number": 1, "retained_customers": 1, "retention_pct": 50.0},
        ],
    }]


def test_customer_route_passes_filters_to_analytics(monkeypatch):
    observed = {}

    def customers(**kwargs):
        observed.update(kwargs)
        return {"summary": {"known_customers": 1}}

    monkeypatch.setattr("biznexa.main.customer_analytics.customers", customers)
    response = request(
        "GET",
        "/api/analytics/synthetic/customers?start=2024-01-01&end=2024-01-31"
        "&year=2024&month=1&search=abc&segment=New&activity_status=active"
        "&rfm_segment=Champions&min_revenue=10&max_revenue=50&page=2&page_size=10",
    )

    assert response.status_code == 200
    assert observed == {
        "start": "2024-01-01",
        "end": "2024-01-31",
        "year": 2024,
        "month": 1,
        "search": "abc",
        "segment": "New",
        "activity_status": "active",
        "rfm_segment": "Champions",
        "min_revenue": 10,
        "max_revenue": 50,
        "page": 2,
        "page_size": 10,
    }


def test_customer_route_validates_page_size():
    response = request(
        "GET",
        "/api/analytics/synthetic/customers?page_size=500",
    )

    assert response.status_code == 422


def test_customer_detail_route_passes_customer_id_and_as_of(monkeypatch):
    observed = {}

    def customer_detail(customer_id, as_of):
        observed.update(customer_id=customer_id, as_of=as_of)
        return {"customer": {"customer_id": customer_id}}

    monkeypatch.setattr(
        "biznexa.main.customer_analytics.customer_detail", customer_detail
    )
    response = request(
        "GET",
        "/api/analytics/synthetic/customers/C-100?as_of=2024-12-31",
    )

    assert response.status_code == 200
    assert observed == {"customer_id": "C-100", "as_of": "2024-12-31"}
