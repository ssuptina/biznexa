# Decision Intelligence

Business Pulse signals are calculated from the configured PostgreSQL analytics schema. Sales comparisons use equal-length periods; customer inactivity, inventory thresholds, and supplier receipt definitions are disclosed with each signal. Missing source evidence suppresses a signal rather than supplying an estimate.

The What-if Simulator is read-only: projected revenue = baseline revenue × (1 + sales growth) + baseline average revenue per buyer × buyers × retention change; projected cost of goods sold = baseline cost of goods sold × (1 + product-cost change); projected gross profit = projected revenue − projected cost of goods sold. Inventory value is adjusted separately. These are arithmetic scenarios, not forecasts.

Decision Impact records are stored in the app-managed `business_decision` PostgreSQL table, separate from imported analytics data. A decision captures its selected metric over an equal-length baseline immediately before the decision date. A later review records the same metric over the configured post-decision window. The comparison is descriptive and does not establish causation. Metric values and periods are retained with each record; unavailable baselines and review data remain explicit.

The tracker schema is introduced by Alembic revision `0002_business_decisions`, following `0001_sales_foundation`. Check the configured database's Alembic revision before applying migrations; upgrading from an uninitialized database also applies the existing initial persistence migration.
