from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biznexa.db import Base


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("source_system", "source_id", name="uq_customer_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    orders: Mapped[list["SalesOrder"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("source_system", "source_id", name="uq_product_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    base_uom: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order_lines: Mapped[list["SalesOrderLine"]] = relationship(back_populates="product")


class SalesOrder(Base):
    __tablename__ = "sales_order"
    __table_args__ = (
        UniqueConstraint("source_system", "source_id", name="uq_sales_order_source"),
        CheckConstraint("status IN ('draft', 'confirmed', 'fulfilled', 'cancelled')", name="ck_sales_order_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="orders")
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"
    __table_args__ = (
        UniqueConstraint("source_system", "source_id", name="uq_sales_order_line_source"),
        CheckConstraint("quantity > 0", name="ck_sales_order_line_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_order_line_unit_price_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_sales_order_line_discount_nonnegative"),
        CheckConstraint("unit_cost_at_sale >= 0", name="ck_sales_order_line_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    unit_cost_at_sale: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    order: Mapped[SalesOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship(back_populates="order_lines")
