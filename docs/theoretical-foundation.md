# Theoretical foundation

BizNexa is built around a simple BI workflow: collect business records, validate the schema, calculate metrics, present findings, and let humans interpret the result.

## Core ideas

- Descriptive analytics shows what happened.
- Diagnostic analytics explains why it happened.
- Decision support highlights threshold-based signals.
- Predictive analytics must be validated before being treated as a real forecast.

## Metrics and reporting

- Every metric needs a clear grain and a time scope.
- Ratios should be recalculated from totals, not averaged from row-level percentages.
- Snapshot metrics like inventory value should be treated as point-in-time values.

## Governance

- Business owners must approve KPI definitions.
- Access control, privacy, and data retention must be defined before production use.
- The app should surface limits clearly instead of hiding them.

## Reference

- [Architecture](./architecture.md)
- [Data flow](./data-flow.md)
- [KPI dictionary](./kpi-dictionary.md)
