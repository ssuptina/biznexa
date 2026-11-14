# Data flow

```text
User → Frontend → API → PostgreSQL schema → Charts and KPI views
```

## Flow

1. The frontend sends reporting parameters.
2. FastAPI validates the request and reads the configured schema.
3. SQLAlchemy/psycopg runs queries against PostgreSQL.
4. The backend returns aggregates and context.
5. The UI renders charts, cards, and tables.

## Notes

- Local Vite dev uses a proxy to the backend.
- The application reads from the configured analytics schema.
- Synthetic data is explicit and separate from runtime production data.
- `/health` and `/health/db` run real checks before reporting readiness.
