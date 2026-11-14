# BizNexa system diagram

```mermaid
flowchart LR
    U[User] --> UI[React frontend\nApp.tsx + components]
    UI --> F[API helper\nfrontend/src/services/api.ts]
    F --> API[FastAPI backend\nbackend/biznexa/main.py]
    API --> V[Validation layer\nquery params + request models]
    V --> A[Analytics layer\nanalytics.py + customer_analytics.py]
    A --> SQL[SQLAlchemy / PostgreSQL queries]
    SQL --> DB[(PostgreSQL analytics schema)]
    DB --> A
    A --> JSON[JSON response]
    JSON --> UI
    UI --> CHARTS[Charts, KPI cards, tables, filters]

    subgraph Frontend
        UI
        F
        CHARTS
    end

    subgraph Backend
        API
        V
        A
        SQL
    end

    subgraph Data
        DB
    end
```

## Diagram explanation

This diagram shows the real data path in BizNexa.

- The user interacts with the dashboard UI.
- The frontend sends HTTP requests through the central API helper.
- FastAPI validates the request and routes it to analytics functions.
- The analytics layer runs SQL against PostgreSQL.
- PostgreSQL returns aggregated business data.
- The frontend converts that data into cards, charts, and insight widgets.

## The most important principle

The frontend is not the source of truth for metrics. The backend and PostgreSQL are.
