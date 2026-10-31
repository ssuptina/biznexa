import { useEffect, useState, type FormEvent } from 'react'
import { apiGet, apiPost, ApiRequestError } from '../services/api'

type MetricKey =
  | 'gross_sales_usd'
  | 'gross_profit_usd'
  | 'gross_margin_pct'
  | 'order_count'
  | 'inventory_value_usd'
  | 'low_stock_count'
  | 'supplier_on_time_rate_pct'

type DecisionRecord = {
  id: number
  title: string
  expected_outcome: string
  decision_date: string
  metric_key: MetricKey
  metric_label: string
  metric_unit: string
  metric_methodology: string
  review_after_days: number
  baseline_period: { start: string; end: string }
  baseline_value: string | null
  baseline_available: boolean
  review_period: { start: string; end: string }
  observed_value: string | null
  change_from_baseline?: string | null
  reviewed_at: string | null
  reviewable: boolean
  status: string
  causality_note?: string
}

type DecisionResponse = {
  records: DecisionRecord[]
  storage: string
  causality_note: string
}

const metrics: { key: MetricKey; label: string; unit: string }[] = [
  { key: 'gross_sales_usd', label: 'Gross sales', unit: 'USD' },
  { key: 'gross_profit_usd', label: 'Gross profit', unit: 'USD' },
  { key: 'gross_margin_pct', label: 'Gross margin', unit: '%' },
  { key: 'order_count', label: 'Order count', unit: 'orders' },
  { key: 'inventory_value_usd', label: 'Inventory value', unit: 'USD' },
  { key: 'low_stock_count', label: 'Low-stock locations', unit: 'locations' },
  { key: 'supplier_on_time_rate_pct', label: 'Supplier on-time rate', unit: '%' },
]

const metricDescription: Record<MetricKey, string> = {
  gross_sales_usd: 'Non-cancelled sales line revenue in the period.',
  gross_profit_usd: 'Sales line revenue minus line cost, excluding cancelled orders.',
  gross_margin_pct: 'Gross profit divided by gross sales.',
  order_count: 'Distinct non-cancelled orders.',
  inventory_value_usd: 'Inventory value at the latest snapshot in the period.',
  low_stock_count: 'Product/warehouse rows with fewer than 10 available units at the latest snapshot.',
  supplier_on_time_rate_pct: 'Share of fully received, date-promised purchase-order lines placed in the period and completed by period end that arrived on time.',
}

function metricValue(value: string | null, unit: string) {
  if (value === null) return 'Unavailable'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'Unavailable'
  if (unit === 'USD') return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 2,
  }).format(numeric)
  if (unit === '%') return `${numeric.toFixed(2)}%`
  return `${numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`
}

export function DecisionImpactTracker() {
  const [records, setRecords] = useState<DecisionRecord[]>([])
  const [storage, setStorage] = useState('PostgreSQL')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [expectedOutcome, setExpectedOutcome] = useState('')
  const [decisionDate, setDecisionDate] = useState(new Date().toISOString().slice(0, 10))
  const [metricKey, setMetricKey] = useState<MetricKey>('gross_sales_usd')
  const [reviewDays, setReviewDays] = useState('30')

  async function loadRecords() {
    const response = await apiGet<DecisionResponse>('/api/analytics/synthetic/decision-impact')
    setRecords(response.records)
    setStorage(response.storage)
  }

  useEffect(() => {
    let active = true
    apiGet<DecisionResponse>('/api/analytics/synthetic/decision-impact')
      .then((response) => {
        if (active) {
          setRecords(response.records)
          setStorage(response.storage)
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof ApiRequestError
          ? reason.message
          : 'Decision records could not be loaded.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function saveDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const saved = await apiPost<
        { title: string; expected_outcome: string; decision_date: string; metric_key: MetricKey; review_after_days: number },
        DecisionRecord
      >('/api/analytics/synthetic/decision-impact', {
        title,
        expected_outcome: expectedOutcome,
        decision_date: decisionDate,
        metric_key: metricKey,
        review_after_days: Number(reviewDays),
      })
      setRecords((current) => [saved, ...current])
      setTitle('')
      setExpectedOutcome('')
    } catch (reason) {
      setError(reason instanceof ApiRequestError ? reason.message : 'The decision could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  async function reviewDecision(id: number) {
    setReviewing(id)
    setError(null)
    try {
      const reviewed = await apiPost<Record<string, never>, DecisionRecord>(
        `/api/analytics/synthetic/decision-impact/${id}/review`,
        {},
      )
      setRecords((current) => current.map((record) => record.id === id ? reviewed : record))
    } catch (reason) {
      setError(reason instanceof ApiRequestError ? reason.message : 'The outcome could not be reviewed.')
      try {
        await loadRecords()
      } catch {
        setError((message) => `${message ?? 'The review failed.'} The decision list could not be refreshed.`)
      }
    } finally {
      setReviewing(null)
    }
  }

  return <section className="decision-tracker" aria-labelledby="decision-tracker-title">
    <header className="pulse-header">
      <div>
        <div className="panel-kicker">DECISION FOLLOW-THROUGH</div>
        <h2 id="decision-tracker-title">Decision Impact Tracker</h2>
        <p>Record the decision and review a selected metric after its observation window.</p>
      </div>
      <span className="tracker-storage">{storage} records</span>
    </header>

    {error && <div className="module-error" role="alert"><strong>Decision tracker</strong><span>{error}</span></div>}

    <div className="tracker-layout">
      <form className="tracker-form" onSubmit={saveDecision}>
        <h3>Record a decision</h3>
        <label className="tracker-field">
          <span>Decision</span>
          <input required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="tracker-field">
          <span>Expected outcome</span>
          <textarea required maxLength={2000} rows={3} value={expectedOutcome} onChange={(event) => setExpectedOutcome(event.target.value)} />
        </label>
        <div className="tracker-form-row">
          <label className="tracker-field">
            <span>Decision date</span>
            <input required type="date" value={decisionDate} onChange={(event) => setDecisionDate(event.target.value)} />
          </label>
          <label className="tracker-field">
            <span>Review after (days)</span>
            <input required type="number" min={1} max={3650} value={reviewDays} onChange={(event) => setReviewDays(event.target.value)} />
          </label>
        </div>
        <label className="tracker-field">
          <span>Metric to review</span>
          <select value={metricKey} onChange={(event) => setMetricKey(event.target.value as MetricKey)}>
            {metrics.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
          </select>
          <small>{metricDescription[metricKey]}</small>
        </label>
        <p className="tracker-baseline-note">The baseline is captured from the equal-length period immediately before the decision date. Records are stored in {storage}.</p>
        <button className="whatif-submit" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save decision'}</button>
      </form>

      <div className="tracker-records" aria-live="polite">
        <div className="tracker-records-heading"><h3>Recorded decisions</h3><span>{records.length} shown · up to 100</span></div>
        {loading && <div className="pulse-status" role="status">Loading decision records…</div>}
        {!loading && records.length === 0 && <div className="pulse-empty"><strong>No decisions recorded</strong><span>Saved decisions can be reviewed here when their metric period is available.</span></div>}
        {records.map((record) => <article className="tracker-record" key={record.id}>
          <div className="tracker-record-top">
            <div><h4>{record.title}</h4><span>{record.decision_date} · {record.metric_label}</span></div>
            <span className={`tracker-status ${record.reviewed_at ? 'is-reviewed' : ''}`}>{record.status}</span>
          </div>
          <p className="tracker-expected">{record.expected_outcome}</p>
          <div className="tracker-periods">
            <span><small>Baseline</small>{record.baseline_period.start} — {record.baseline_period.end}</span>
            <span><small>Review window</small>{record.review_period.start} — {record.review_period.end}</span>
          </div>
          <div className="tracker-values">
            <span><small>Baseline</small><b>{metricValue(record.baseline_value, record.metric_unit)}</b></span>
            <span><small>Observed</small><b>{metricValue(record.observed_value, record.metric_unit)}</b></span>
            {record.change_from_baseline !== undefined && <span><small>Difference</small><b>{metricValue(record.change_from_baseline ?? null, record.metric_unit)}</b></span>}
          </div>
          {!record.baseline_available && <p className="tracker-limitation">No complete baseline was available when this decision was recorded.</p>}
          <details className="tracker-method">
            <summary>Metric methodology and limitations</summary>
            <p>{record.metric_methodology}</p>
            <p>Comparison: baseline period versus the selected review window. Results are descriptive and do not establish causation.</p>
          </details>
          {record.reviewable && <button className="tracker-review-button" type="button" disabled={reviewing === record.id} onClick={() => void reviewDecision(record.id)}>
            {reviewing === record.id ? 'Reviewing…' : 'Record outcome'}
          </button>}
        </article>)}
      </div>
    </div>
    <p className="tracker-causality">Observed metric changes are not evidence that a decision caused those changes. Data gaps remain explicit; unavailable metrics are not replaced with estimates.</p>
  </section>
}
