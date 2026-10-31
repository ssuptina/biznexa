from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from biznexa.db import Base


class BusinessDecision(Base):
    __tablename__ = "business_decision"
    __table_args__ = (
        CheckConstraint(
            "review_after_days BETWEEN 1 AND 3650",
            name="ck_business_decision_review_days",
        ),
        CheckConstraint(
            "metric_key IN ('gross_sales_usd', 'gross_profit_usd', "
            "'gross_margin_pct', 'order_count', 'inventory_value_usd', "
            "'low_stock_count', 'supplier_on_time_rate_pct')",
            name="ck_business_decision_metric",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    review_after_days: Mapped[int] = mapped_column(nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    baseline_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    review_start: Mapped[date | None] = mapped_column(Date)
    review_end: Mapped[date | None] = mapped_column(Date)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
