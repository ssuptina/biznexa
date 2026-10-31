import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet, apiPost, ApiRequestError } from '../services/api'

type PulseRecord = { id: string; name: string; module: string }
type PulseInsight = {
  id: string
  title: string
  category: string
  level: string
  supporting_metric: { name: string; current: string; comparison: string | null }
  reporting_period: { start: string; end: string }
  comparison_period: { start: string; end: string } | null
  related_records: PulseRecord[]
  methodology: string
  explanation: string
  next_action: string
  limitations: string[]
}
type PulseSummaryPeriod = {
  gross_sales_usd: string
  gross_profit_usd: string
  gross_margin_pct: string | null
  order_count: number
  inventory_value_usd: string | null
  low_stock_product_count?: number
  inventory_snapshot_date: string | null
}
type PulseResponse = {
  synthetic: boolean
  period: { start: string; end: string }
  comparison_period: { start: string; end: string }
  comparison_available: boolean
  summary: { current: PulseSummaryPeriod; comparison: PulseSummaryPeriod }
  method: string
  insights: PulseInsight[]
  data_limitations: string[]
}

const money = (value: string | null | undefined) => value === null || value === undefined
  ? 'Unavailable'
  : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value))

const periodLabel = (period: { start: string; end: string }) => `${period.start} — ${period.end}`

export function BusinessPulse({
  start,
  end,
  onNavigate,
}: {
  start: string
  end: string
  onNavigate: (section: string) => void
}) {
  const [periodMode, setPeriodMode] = useState<'latest' | 'selected'>('latest')
  const [data, setData] = useState<PulseResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    const params = new URLSearchParams()
    if (periodMode === 'selected') {
      if (start) params.set('start', start)
      if (end) params.set('end', end)
    }
    const query = params.toString()
    setLoading(true)
    setError(null)
    apiGet<PulseResponse>(`/api/analytics/synthetic/business-pulse${query ? `?${query}` : ''}`)
      .then((response) => {
        if (mounted) setData(response)
      })
      .catch((reason: unknown) => {
        if (mounted) setError(
          reason instanceof ApiRequestError ? reason.message : 'Business Pulse could not load validated analytics.',
        )
      })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [periodMode, start, end])

  const chartData = useMemo(() => {
    if (!data) return []
    const rows = [{
      period: 'Current',
      revenue: Number(data.summary.current.gross_sales_usd),
      profit: Number(data.summary.current.gross_profit_usd),
    }]
    if (data.comparison_available) rows.push({
      period: 'Comparison',
      revenue: Number(data.summary.comparison.gross_sales_usd),
      profit: Number(data.summary.comparison.gross_profit_usd),
    })
    return rows
  }, [data])

  return <section className="business-pulse" aria-labelledby="business-pulse-title">
    <header className="pulse-header">
      <div>
        <div className="panel-kicker">CROSS-FUNCTIONAL SIGNALS</div>
        <h2 id="business-pulse-title">Business Pulse</h2>
        <p>Evidence from recorded sales, customer, inventory, and supplier data. No predictive model is claimed.</p>
      </div>
      <label className="pulse-period-select">
        <span>Analysis period</span>
        <select value={periodMode} onChange={(event) => setPeriodMode(event.target.value as 'latest' | 'selected')}>
          <option value="latest">Latest 12 months</option>
          <option value="selected">Selected reporting period</option>
        </select>
      </label>
    </header>

    {loading && <div className="pulse-status" role="status">Loading evidence from PostgreSQL…</div>}
    {error && <div className="module-error" role="alert"><strong>Business Pulse unavailable</strong><span>{error}</span></div>}
    {data && !loading && <>
      <div className="pulse-period-context">
        <span><b>Current</b> {periodLabel(data.period)}</span>
        <span><b>Compared with</b> {data.comparison_available ? periodLabel(data.comparison_period) : 'No comparison sales available'}</span>
        {data.synthetic && <span className="pulse-source">Validated synthetic dataset</span>}
      </div>

      <div className="pulse-evidence-grid">
        <section className="pulse-chart-panel" aria-label="Period revenue and gross profit comparison">
          <div className="pulse-panel-heading">
            <div><span className="panel-kicker">RECORDED PERFORMANCE</span><h3>Revenue and gross profit</h3></div>
            <span className="pulse-period-note">{data.comparison_available ? 'Period comparison' : 'Current period'}</span>
          </div>
          <div className="pulse-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 12, bottom: 2, left: 2 }}>
                <CartesianGrid stroke="#eee9e2" strokeDasharray="2 4" vertical={false}/>
                <XAxis dataKey="period" tickLine={false} axisLine={false} tick={{ fill: '#858078', fontSize: 10 }}/>
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} width={52} tickFormatter={(value: number) => `$${(value / 1000).toFixed(0)}k`}/>
                <Tooltip formatter={(value) => [money(String(value)), '']} contentStyle={{ borderRadius: 6, borderColor: '#e4ded5', fontSize: 10 }}/>
                <Bar dataKey="revenue" name="Revenue" fill="#b87355" radius={[3, 3, 0, 0]} maxBarSize={34}/>
                <Bar dataKey="profit" name="Gross profit" fill="#5a5b54" radius={[3, 3, 0, 0]} maxBarSize={34}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="pulse-chart-legend"><span><i className="pulse-swatch revenue"/>Revenue</span><span><i className="pulse-swatch profit"/>Gross profit</span></div>
          <div className="pulse-chart-footer">
            <span>Current margin <b>{data.summary.current.gross_margin_pct === null ? 'Unavailable' : `${Number(data.summary.current.gross_margin_pct).toFixed(2)}%`}</b></span>
            <span>Orders <b>{data.summary.current.order_count.toLocaleString()}</b></span>
            <span>Inventory value <b>{money(data.summary.current.inventory_value_usd)}</b></span>
          </div>
        </section>

        <section className="pulse-insight-panel" aria-labelledby="pulse-insights-title">
          <div className="pulse-panel-heading">
            <div><span className="panel-kicker">EVIDENCE REVIEW</span><h3 id="pulse-insights-title">Signals to review</h3></div>
            <span className="pulse-insight-count">{data.insights.length}</span>
          </div>
          {data.insights.length ? <div className="pulse-insight-list">
            {data.insights.map((insight) => <article className="pulse-insight-card" key={insight.id}>
              <div className="pulse-insight-meta"><span>{insight.category}</span><span className={`pulse-level pulse-level-${insight.level.toLowerCase()}`}>{insight.level}</span></div>
              <h4>{insight.title}</h4>
              <p>{insight.explanation}</p>
              <div className="pulse-metric"><span>{insight.supporting_metric.name}</span><strong>{insight.supporting_metric.current}</strong>
                {insight.supporting_metric.comparison !== null && <small>Comparison: {insight.supporting_metric.comparison}</small>}
              </div>
              <details className="pulse-why">
                <summary>Why am I seeing this?</summary>
                <p>{insight.methodology}</p>
                <p><b>Suggested next action:</b> {insight.next_action}</p>
                {insight.limitations.map((limitation) => <p className="pulse-limitation" key={limitation}><b>Limitation:</b> {limitation}</p>)}
              </details>
              {insight.related_records.length > 0 && <div className="pulse-related">
                <span>Related records</span>
                {insight.related_records.map((record) => <button key={`${record.module}-${record.id}`} type="button" onClick={() => onNavigate(record.module)}>{record.name}<span>Open {record.module}</span></button>)}
              </div>}
            </article>)}
          </div> : <div className="pulse-empty">
            <strong>No evidence-backed signals for this period</strong>
            <span>{data.comparison_available ? 'The configured rules did not identify a qualifying change.' : 'The prior period has no sales records, so temporal signals are suppressed.'}</span>
          </div>}
        </section>
      </div>
      <details className="pulse-method">
        <summary>Method and data limitations</summary>
        <p>{data.method}</p>
        {data.data_limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
      </details>
    </>}
  </section>
}

type ScenarioResponse = {
  synthetic: boolean
  has_sales_data: boolean
  baseline_period: { start: string; end: string }
  actual_baseline: {
    gross_sales_usd: string
    cogs_usd: string
    gross_profit_usd: string
    gross_margin_pct: string | null
    order_count: number
    customer_count: number
    average_revenue_per_customer_usd: string
    inventory_value_usd: string | null
    inventory_snapshot_date: string | null
  }
  scenario: {
    projected_revenue_usd: string
    retention_revenue_change_usd: string
    projected_cogs_usd: string
    projected_gross_profit_usd: string
    projected_gross_margin_pct: string | null
    projected_inventory_value_usd: string | null
    gross_profit_at_target_margin_usd: string | null
    target_margin_profit_gap_usd: string | null
  }
  formulas: string[]
  limitations: string[]
}
type ScenarioRequest = {
  sales_growth_pct: number
  product_cost_change_pct: number
  retention_change_pct: number
  inventory_change_pct: number
  gross_margin_target_pct: number | null
}

const scenarioInputs = [
  { key: 'sales_growth_pct', label: 'Sales growth', min: -100, max: 1000 },
  { key: 'product_cost_change_pct', label: 'Product cost change', min: -100, max: 1000 },
  { key: 'retention_change_pct', label: 'Retention change', min: -100, max: 100 },
  { key: 'inventory_change_pct', label: 'Inventory change', min: -100, max: 1000 },
] as const

export function WhatIfSimulator({ start, end }: { start: string; end: string }) {
  const [periodMode, setPeriodMode] = useState<'latest' | 'selected'>('latest')
  const [assumptions, setAssumptions] = useState({
    sales_growth_pct: '0',
    product_cost_change_pct: '0',
    retention_change_pct: '0',
    inventory_change_pct: '0',
    gross_margin_target_pct: '',
  })
  const [result, setResult] = useState<ScenarioResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const chartData = useMemo(() => result ? [
    {
      period: 'Recorded baseline',
      revenue: Number(result.actual_baseline.gross_sales_usd),
      profit: Number(result.actual_baseline.gross_profit_usd),
    },
    {
      period: 'Scenario',
      revenue: Number(result.scenario.projected_revenue_usd),
      profit: Number(result.scenario.projected_gross_profit_usd),
    },
  ] : [], [result])

  async function submitScenario(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (periodMode === 'selected') {
      if (start) params.set('start', start)
      if (end) params.set('end', end)
    }
    const query = params.toString()
    try {
      const response = await apiPost<ScenarioRequest, ScenarioResponse>(
        `/api/analytics/synthetic/scenario${query ? `?${query}` : ''}`,
        {
          ...assumptions,
          sales_growth_pct: Number(assumptions.sales_growth_pct),
          product_cost_change_pct: Number(assumptions.product_cost_change_pct),
          retention_change_pct: Number(assumptions.retention_change_pct),
          inventory_change_pct: Number(assumptions.inventory_change_pct),
          gross_margin_target_pct: assumptions.gross_margin_target_pct === ''
            ? null
            : Number(assumptions.gross_margin_target_pct),
        },
      )
      setResult(response)
    } catch (reason) {
      setError(reason instanceof ApiRequestError ? reason.message : 'The scenario could not be calculated.')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return <section className="whatif-workspace" aria-labelledby="whatif-title">
    <header className="pulse-header">
      <div>
        <div className="panel-kicker">SCENARIO ANALYSIS</div>
        <h2 id="whatif-title">What-if Simulator</h2>
        <p>Adjust assumptions against recorded baselines. Calculations are isolated from business records.</p>
      </div>
      <label className="pulse-period-select">
        <span>Baseline period</span>
        <select value={periodMode} onChange={(event) => setPeriodMode(event.target.value as 'latest' | 'selected')}>
          <option value="latest">Latest 12 months</option>
          <option value="selected">Selected reporting period</option>
        </select>
      </label>
    </header>

    <div className="whatif-grid">
      <form className="whatif-form" onSubmit={submitScenario}>
        <div className="whatif-form-heading"><strong>Scenario assumptions</strong><span>Not actual results</span></div>
        <div className="whatif-input-grid">
          {scenarioInputs.map((input) => <label className="whatif-field" key={input.key}>
            <span>{input.label} <small>(%)</small></span>
            <input
              type="number"
              step="0.1"
              min={input.min}
              max={input.max}
              required
              value={assumptions[input.key]}
              onChange={(event) => setAssumptions((current) => ({ ...current, [input.key]: event.target.value }))}
            />
          </label>)}
          <label className="whatif-field">
            <span>Target gross margin <small>(%, optional)</small></span>
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={assumptions.gross_margin_target_pct}
              onChange={(event) => setAssumptions((current) => ({ ...current, gross_margin_target_pct: event.target.value }))}
            />
          </label>
        </div>
        {error && <div className="module-error" role="alert"><strong>Scenario unavailable</strong><span>{error}</span></div>}
        <button className="whatif-submit" type="submit" disabled={loading}>{loading ? 'Calculating…' : 'Calculate scenario'}</button>
      </form>

      <section className="whatif-results" aria-live="polite">
        {!result && !loading && <div className="pulse-empty"><strong>No scenario calculated</strong><span>Enter assumptions and calculate to compare them with actual baseline data.</span></div>}
        {loading && <div className="pulse-status" role="status">Calculating against the configured PostgreSQL data…</div>}
        {result && <>
          <div className="whatif-result-heading">
            <div><span className="panel-kicker">RECORDED BASELINE VS ASSUMPTIONS</span><strong>Scenario comparison</strong></div>
            <span>{periodLabel(result.baseline_period)}</span>
          </div>
          {!result.has_sales_data && <div className="whatif-no-data" role="status">No sales records exist in this baseline period; revenue and margin results are zero or unavailable.</div>}
          <div className="pulse-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 12, bottom: 2, left: 2 }}>
                <CartesianGrid stroke="#eee9e2" strokeDasharray="2 4" vertical={false}/>
                <XAxis dataKey="period" tickLine={false} axisLine={false} tick={{ fill: '#858078', fontSize: 9 }}/>
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} width={52} tickFormatter={(value: number) => `$${(value / 1000).toFixed(0)}k`}/>
                <Tooltip formatter={(value) => [money(String(value)), '']} contentStyle={{ borderRadius: 6, borderColor: '#e4ded5', fontSize: 10 }}/>
                <Bar dataKey="revenue" name="Revenue" fill="#b87355" radius={[3, 3, 0, 0]} maxBarSize={34}/>
                <Bar dataKey="profit" name="Gross profit" fill="#5a5b54" radius={[3, 3, 0, 0]} maxBarSize={34}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="whatif-column-labels"><span>Metric</span><span>Actual baseline</span><span>Scenario output</span></div>
          <div className="whatif-metric-table">
            <div><span>Revenue</span><b>{money(result.actual_baseline.gross_sales_usd)}</b><b>{money(result.scenario.projected_revenue_usd)}</b></div>
            <div><span>Gross profit</span><b>{money(result.actual_baseline.gross_profit_usd)}</b><b>{money(result.scenario.projected_gross_profit_usd)}</b></div>
            <div><span>Gross margin</span><b>{result.actual_baseline.gross_margin_pct === null ? 'Unavailable' : `${Number(result.actual_baseline.gross_margin_pct).toFixed(2)}%`}</b><b>{result.scenario.projected_gross_margin_pct === null ? 'Unavailable' : `${Number(result.scenario.projected_gross_margin_pct).toFixed(2)}%`}</b></div>
            <div><span>Inventory value</span><b>{money(result.actual_baseline.inventory_value_usd)}</b><b>{money(result.scenario.projected_inventory_value_usd)}</b></div>
            {result.scenario.gross_profit_at_target_margin_usd !== null && <div><span>Target-margin profit / gap</span><b>{money(result.scenario.gross_profit_at_target_margin_usd)}</b><b>{money(result.scenario.target_margin_profit_gap_usd)}</b></div>}
          </div>
          <details className="pulse-method">
            <summary>Formula and limitations</summary>
            {result.formulas.map((formula) => <p key={formula}>{formula}</p>)}
            {result.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
          </details>
        </>}
      </section>
    </div>
  </section>
}
