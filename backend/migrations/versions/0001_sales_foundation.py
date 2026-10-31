"""Create the initial sales-domain persistence model.

Revision ID: 0001_sales_foundation
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_sales_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_system", "source_id", name="uq_customer_source"),
    )
    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("base_uom", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_system", "source_id", name="uq_product_source"),
    )
    op.create_table(
        "sales_order",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_system", "source_id", name="uq_sales_order_source"),
        sa.CheckConstraint("status IN ('draft', 'confirmed', 'fulfilled', 'cancelled')", name="ck_sales_order_status"),
    )
    op.create_index("ix_sales_order_customer_id", "sales_order", ["customer_id"])
    op.create_index("ix_sales_order_ordered_at", "sales_order", ["ordered_at"])
    op.create_table(
        "sales_order_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("sales_order.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("discount_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost_at_sale", sa.Numeric(19, 4), nullable=False),
        sa.UniqueConstraint("source_system", "source_id", name="uq_sales_order_line_source"),
        sa.CheckConstraint("quantity > 0", name="ck_sales_order_line_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_order_line_unit_price_nonnegative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_sales_order_line_discount_nonnegative"),
        sa.CheckConstraint("unit_cost_at_sale >= 0", name="ck_sales_order_line_cost_nonnegative"),
    )
    op.create_index("ix_sales_order_line_order_id", "sales_order_line", ["order_id"])
    op.create_index("ix_sales_order_line_product_id", "sales_order_line", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_order_line_product_id", table_name="sales_order_line")
    op.drop_index("ix_sales_order_line_order_id", table_name="sales_order_line")
    op.drop_table("sales_order_line")
    op.drop_index("ix_sales_order_ordered_at", table_name="sales_order")
    op.drop_index("ix_sales_order_customer_id", table_name="sales_order")
    op.drop_table("sales_order")
    op.drop_table("product")
    op.drop_table("customer")
