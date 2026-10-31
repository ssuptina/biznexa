"""Persist decision records and their measured outcomes.

Revision ID: 0002_business_decisions
Revises: 0001_sales_foundation
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_business_decisions"
down_revision = "0001_sales_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_decision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.String(64), nullable=False),
        sa.Column("review_after_days", sa.Integer(), nullable=False),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column("baseline_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("baseline_available", sa.Boolean(), nullable=False),
        sa.Column("review_start", sa.Date(), nullable=True),
        sa.Column("review_end", sa.Date(), nullable=True),
        sa.Column("observed_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "review_after_days BETWEEN 1 AND 3650",
            name="ck_business_decision_review_days",
        ),
        sa.CheckConstraint(
            "metric_key IN ('gross_sales_usd', 'gross_profit_usd', "
            "'gross_margin_pct', 'order_count', 'inventory_value_usd', "
            "'low_stock_count', 'supplier_on_time_rate_pct')",
            name="ck_business_decision_metric",
        ),
    )
    op.create_index(
        "ix_business_decision_decision_date",
        "business_decision",
        ["decision_date"],
    )
    op.create_index(
        "ix_business_decision_metric_key",
        "business_decision",
        ["metric_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_business_decision_metric_key", table_name="business_decision")
    op.drop_index("ix_business_decision_decision_date", table_name="business_decision")
    op.drop_table("business_decision")
