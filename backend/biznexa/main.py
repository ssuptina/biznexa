"""BizNexa HTTP API."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, TypeVar

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from biznexa import analytics, customer_analytics, decision_intelligence, decision_tracker
from biznexa.db import database_health

logger = logging.getLogger(__name__)

app = FastAPI(
    title="BizNexa API",
    summary="Business intelligence and decision analytics platform",
    version="0.2.0",
)

T = TypeVar("T")


class ScenarioAssumptions(BaseModel):
    sales_growth_pct: Decimal = Field(default=Decimal(0), ge=-100, le=1000)
    product_cost_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=1000)
    retention_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=100)
    inventory_change_pct: Decimal = Field(default=Decimal(0), ge=-100, le=1000)
    gross_margin_target_pct: Decimal | None = Field(default=None, ge=0, le=100)


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    expected_outcome: str = Field(min_length=1, max_length=2000)
    decision_date: date
    metric_key: Literal[
        "gross_sales_usd",
        "gross_profit_usd",
        "gross_margin_pct",
        "order_count",
        "inventory_value_usd",
        "low_stock_count",
        "supplier_on_time_rate_pct",
    ]
    review_after_days: int = Field(default=30, ge=1, le=3650)

    @field_validator("title", "expected_outcome")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field must contain non-whitespace text.")
        return value


def _run_analytics(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Analytics query failed")
        raise HTTPException(
            status_code=503,
            detail="Analytics query failed. Check database availability and the required schema.",
        ) from exc


@app.get("/health", tags=["operations"])
def health() -> dict[str, object]:
    """Report process health and the result of a real database query."""
    db = database_health()
    ready = db["status"] == "ok" and bool(db.get("analytics_schema_initialized"))
    return {"status": "ok" if ready else "degraded", "database": db}


@app.get("/health/db", tags=["operations"])
def database_health_endpoint() -> dict[str, object]:
    result = database_health()
    if result["status"] != "ok" or not result.get("analytics_schema_initialized"):
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/api/analytics/synthetic/overview", tags=["analytics"])
def synthetic_overview(
    start: str | None = Query(default=None, description="Inclusive ISO date"),
    end: str | None = Query(default=None, description="Inclusive ISO date"),
    granularity: Literal["day", "week", "month", "quarter", "year"] = "month",
    comparison: Literal["previous_period", "same_period_last_year", "none"] = "previous_period",
    include_daily_sales: bool = True,
) -> dict[str, object]:
    return _run_analytics(lambda: analytics.overview(
        start, end, granularity, comparison, include_daily_sales
    ))


@app.get("/api/analytics/synthetic/sales", tags=["analytics"])
def synthetic_sales(
    start: str | None = None,
    end: str | None = None,
    granularity: Literal["day", "week", "month", "quarter", "year"] = "month",
) -> dict[str, object]:
    return _run_analytics(lambda: analytics.sales(start, end, granularity))


@app.get("/api/analytics/synthetic/customers", tags=["analytics"])
def synthetic_customers(
    start: str | None = Query(default=None, description="Inclusive ISO date"),
    end: str | None = Query(default=None, description="Inclusive ISO date"),
    year: int | None = Query(default=None, ge=1900, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    search: str | None = Query(default=None, max_length=160),
    segment: str | None = None,
    activity_status: Literal["active", "inactive"] | None = None,
    rfm_segment: str | None = None,
    min_revenue: Annotated[Decimal | None, Query()] = None,
    max_revenue: Annotated[Decimal | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    return _run_analytics(lambda: customer_analytics.customers(
        start=start,
        end=end,
        year=year,
        month=month,
        search=search,
        segment=segment,
        activity_status=activity_status,
        rfm_segment=rfm_segment,
        min_revenue=min_revenue,
        max_revenue=max_revenue,
        page=page,
        page_size=page_size,
    ))


@app.get("/api/analytics/synthetic/customers/{customer_id}", tags=["analytics"])
def synthetic_customer_detail(
    customer_id: str,
    as_of: str | None = Query(default=None, description="Inclusive ISO date"),
) -> dict[str, object]:
    return _run_analytics(lambda: customer_analytics.customer_detail(customer_id, as_of))


@app.get("/api/analytics/synthetic/finance", tags=["analytics"])
def synthetic_finance(start: str | None = None, end: str | None = None) -> dict[str, object]:
    return _run_analytics(lambda: analytics.finance(start, end))


@app.get("/api/analytics/synthetic/inventory", tags=["analytics"])
def synthetic_inventory(
    as_of: str | None = None,
    low_stock_threshold: int = Query(default=10, ge=0),
) -> dict[str, object]:
    return _run_analytics(lambda: analytics.inventory(as_of, low_stock_threshold))


@app.get("/api/analytics/synthetic/suppliers", tags=["analytics"])
def synthetic_suppliers(start: str | None = None, end: str | None = None) -> dict[str, object]:
    return _run_analytics(lambda: analytics.suppliers(start, end))


@app.get("/api/analytics/synthetic/decisions", tags=["analytics"])
def synthetic_decisions(start: str | None = None, end: str | None = None) -> dict[str, object]:
    return _run_analytics(lambda: analytics.decisions(start, end))


@app.get("/api/analytics/synthetic/business-pulse", tags=["analytics"])
def business_pulse(
    start: str | None = Query(default=None, description="Inclusive ISO date"),
    end: str | None = Query(default=None, description="Inclusive ISO date"),
) -> dict[str, object]:
    return _run_analytics(lambda: decision_intelligence.business_pulse(start, end))


@app.post("/api/analytics/synthetic/scenario", tags=["analytics"])
def synthetic_scenario(
    assumptions: ScenarioAssumptions,
    start: str | None = Query(default=None, description="Inclusive ISO date"),
    end: str | None = Query(default=None, description="Inclusive ISO date"),
) -> dict[str, object]:
    return _run_analytics(lambda: decision_intelligence.what_if_scenario(
        assumptions.model_dump(), start, end
    ))


@app.get("/api/analytics/synthetic/decision-impact", tags=["analytics"])
def list_decision_impact() -> dict[str, object]:
    return _run_analytics(decision_tracker.list_decisions)


@app.post("/api/analytics/synthetic/decision-impact", tags=["analytics"])
def create_decision_impact(decision: DecisionCreate) -> dict[str, object]:
    return _run_analytics(lambda: decision_tracker.create_decision(
        title=decision.title,
        expected_outcome=decision.expected_outcome,
        decision_date=decision.decision_date,
        metric_key=decision.metric_key,
        review_after_days=decision.review_after_days,
    ))


@app.post("/api/analytics/synthetic/decision-impact/{decision_id}/review", tags=["analytics"])
def review_decision_impact(decision_id: int = Path(ge=1)) -> dict[str, object]:
    try:
        return decision_tracker.review_decision(decision_id)
    except decision_tracker.DecisionTrackerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except decision_tracker.ReviewDataUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Decision review failed")
        raise HTTPException(
            status_code=503,
            detail="Decision review failed. Check database availability and the required schema.",
        ) from exc
