# KPI dictionary

This is the short working definition for the demo metrics in BizNexa. All numbers are synthetic and should be reviewed before production use.

| KPI | Definition | Notes |
|---|---|---|
| Total revenue | Sales value after discounts and refunds, using the approved revenue policy. | Demo only. Rules for tax, shipping, and returns are not final. |
| Gross profit | Net sales minus cost of goods sold. | Not the same as operating profit. |
| Gross margin % | Gross profit divided by net sales. | Calculated from totals, not averaged row-by-row. |
| Active customers | Distinct customers with at least one qualifying purchase in the selected period. | Definition and date rules are still being confirmed. |
| Inventory value | On-hand stock multiplied by the approved cost basis at a point in time. | Snapshot measure; do not sum daily balances into a period total. |
| Revenue by category | Sales for each category as a share of total sales. | Demo mix only; historical category logic is not final. |
| Customer churn risk | Risk band based on a demo model output. | Not a validated production model. |
| Healthy stock share | Share of stock that meets the approved inventory health rule. | Demo only. Thresholds and source logic need approval. |
| Product growth % | Current-period revenue compared with the same period last year or prior period. | Comparison window and seasonality still need business sign-off. |

## Simple rules

- Treat all values as synthetic unless a business owner approves them.
- Ratios should be recalculated from final totals.
- Snapshot metrics need a consistent date and source.
- Finance, inventory, and customer definitions must be approved before production use.
