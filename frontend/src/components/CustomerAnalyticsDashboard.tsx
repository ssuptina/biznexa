import { lazy, Suspense, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { apiGet, ApiRequestError } from '../services/api'

const CustomerSegmentDonut = lazy(() => import('./AnalyticsCharts').then((module) => ({ default: module.CustomerSegmentDonut })))
const CustomerBarChart = lazy(() => import('./AnalyticsCharts').then((module) => ({ default: module.CustomerBarChart })))
const CustomerTrendChart = lazy(() => import('./AnalyticsCharts').then((module) => ({ default: module.CustomerTrendChart })))

type CustomerRecord = {
  customer_id: string | number
  customer_name: string | null
  first_purchase: string | null
  last_purchase: string | null
  total_orders: number
  lifetime_net_sales_usd: string
  period_order_count: number
  period_net_sales_usd: string
  average_order_value_usd: string
  days_since_last_purchase: number | null
  customer_segment: string
  activity_status: 'active' | 'inactive'
  recency_score: number | null
  frequency_score: number | null
  monetary_score: number | null
  rfm_segment: string
}

type CustomerDetail = {
  customer: {
    customer_id: string | number
    customer_name: string | null
    first_purchase: string | null
    last_purchase: string | null
    total_orders: number
    gross_sales_usd: string
    refunds_usd: string
    net_sales_usd: string
    days_since_last_purchase: number | null
    inactivity_status: 'active' | 'inactive'
  }
  as_of: string
  inactivity_days: number
  purchase_history: {
    order_id: string | number
    order_date: string
    gross_sales_usd: string
    refunds_usd: string
    net_sales_usd: string
    product_count: number
  }[]
  product_preferences: {
    product_id: string | number
    product_name: string
    category: string
    order_count: number
    gross_sales_usd: string
  }[]
}

type CustomerAnalytics = {
  period: { start: string; end: string }
  available_period: { start: string; end: string }
  inactivity_days: number
  summary: Record<string, number | string>
  comparison: {
    start: string
    end: string
    metrics: { metric: string; current: number | string; previous: number | string; change_pct: string | null }[]
  }
  segments: {
    segment: string
    customers: number
    period_net_sales_usd: string
    average_order_value_usd: string
  }[]
  monthly_trend: {
    month: string
    active_customers: number
    new_customers: number
    returning_customers: number
    net_sales_usd: string
  }[]
  cohorts: {
    cohort_month: string
    cohort_size: number
    retention: { month_number: number; retained_customers: number; retention_pct: number }[]
  }[]
  purchase_frequency_distribution: { order_frequency: string; customers: number }[]
  customer_value_distribution: {
    value_quintile: number
    customers: number
    minimum_net_sales_usd: string
    maximum_net_sales_usd: string
  }[]
  rfm_segments: { rfm_segment: string; customers: number }[]
  customers: CustomerRecord[]
  pagination: { page: number; page_size: number; total: number }
}

type CustomerFilters = {
  search: string
  segment: string
  activity: string
  rfm: string
  minRevenue: string
  maxRevenue: string
  year: string
  month: string
  page: number
}

type ReportingPeriodPreset = 'last_12_months' | 'last_90_days' | 'year_to_date' | 'all' | 'custom'

const initialFilters: CustomerFilters = {
  search: '',
  segment: '',
  activity: '',
  rfm: '',
  minRevenue: '',
  maxRevenue: '',
  year: '',
  month: '',
  page: 1,
}

function dateOnly(date: Date) {
  return date.toISOString().slice(0, 10)
}

function getReportingPeriod(
  preset: ReportingPeriodPreset,
  availableStart: string,
  availableEnd: string,
  customStart: string,
  customEnd: string,
): [string, string] {
  if (preset === 'all') return ['', '']
  if (preset === 'custom') return [customStart, customEnd]

  const endDate = new Date(`${availableEnd}T00:00:00Z`)
  if (!availableEnd || Number.isNaN(endDate.getTime())) return ['', '']

  const startDate = new Date(endDate)
  if (preset === 'last_12_months') {
    startDate.setUTCMonth(startDate.getUTCMonth() - 12)
    startDate.setUTCDate(startDate.getUTCDate() + 1)
  } else if (preset === 'last_90_days') {
    startDate.setUTCDate(startDate.getUTCDate() - 89)
  } else {
    startDate.setUTCMonth(0, 1)
  }

  const start = dateOnly(startDate)
  return [
    availableStart && start < availableStart ? availableStart : start,
    availableEnd,
  ]
}

const segmentColors: Record<string, string> = {
  New: '#b87355',
  Returning: '#5a5b54',
  'No purchase in selected period': '#aaa18f',
}

const money = (value: string | number | undefined) => {
  const amount = Number(value)
  return Number.isFinite(amount)
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amount)
    : '—'
}

const number = (value: string | number | undefined) => {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount.toLocaleString('en-US', { maximumFractionDigits: 4 }) : '—'
}

function DeferredChart({ className, children }: { className: string; children: ReactNode }) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!container) return
    if (!('IntersectionObserver' in window)) {
      setVisible(true)
      return
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true)
        observer.disconnect()
      }
    }, { rootMargin: '160px' })
    observer.observe(container)
    return () => observer.disconnect()
  }, [container])

  return <div ref={setContainer} className={className}>
    {visible ? children : <div className="customer-chart-loading" style={{ height: '100%' }}/>}
  </div>
}

function metricChange(data: CustomerAnalytics, key: string) {
  const metric = data.comparison.metrics.find((item) => item.metric === key)
  return metric ? { ...metric, start: data.comparison.start, end: data.comparison.end } : undefined
}

function customerSegmentExplanation(segment: string) {
  if (segment === 'New') return 'First qualifying purchase falls within the selected reporting period.'
  if (segment === 'Returning') return 'Purchased in the selected period and had purchased before it.'
  return 'No qualifying purchase in the selected period; this includes customers with no purchase history.'
}

function rfmSegmentExplanation(segment: string) {
  const explanations: Record<string, string> = {
    Champions: 'Recent, frequent customers with high lifetime net sales.',
    'Loyal customers': 'Recent customers with a high qualifying-order frequency.',
    'Potential loyalists': 'Recent customers with at least moderate order frequency.',
    'New customers': 'Exactly one qualifying order, first purchased within the last 30 days.',
    'At-risk customers': 'Low recency with at least moderate order frequency.',
    'Customers needing attention': 'Low recency and low order frequency.',
    'Hibernating customers': 'Remaining purchasing customers outside the rules above.',
    'Unscored - no purchase history': 'RFM is not calculated because no qualifying purchase exists.',
  }
  return explanations[segment] ?? 'Rule-based historical classification; not a prediction.'
}

function MetricCard({
  label,
  value,
  detail,
  comparison,
  help,
}: {
  label: string
  value: string
  detail: string
  comparison?: { start: string; end: string; change_pct: string | null }
  help: string
}) {
  return <article className="customer-metric-card" title={help}>
    <div className="customer-metric-label"><span>{label}</span><span className="customer-help" aria-label={help} title={help}>i</span></div>
    <strong className="customer-metric-value">{value}</strong>
    <div className="customer-metric-foot">
      <span>{detail}</span>
      {comparison && <span className="customer-metric-change">
        {comparison.change_pct === null ? '—' : `${Number(comparison.change_pct) >= 0 ? '+' : ''}${Number(comparison.change_pct).toFixed(1)}%`}
        <small title={`Compared with ${comparison.start} through ${comparison.end}`}> vs {comparison.start}–{comparison.end}</small>
      </span>}
    </div>
  </article>
}

function ChartPanel({
  kicker,
  title,
  description,
  children,
}: {
  kicker: string
  title: string
  description?: string
  children: ReactNode
}) {
  return <article className="surface customer-panel">
    <div className="customer-panel-heading">
      <div><div className="panel-kicker">{kicker}</div><h2>{title}</h2>{description && <p>{description}</p>}</div>
    </div>
    {children}
  </article>
}

export function CustomerAnalyticsDashboard({
  start,
  end,
  availablePeriod,
  overviewLoading,
  initialTab,
  onTabChange,
  onPeriodChange,
}: {
  start: string
  end: string
  availablePeriod: { start: string; end: string } | null
  overviewLoading: boolean
  initialTab: string | null
  onTabChange: (tab: string | null) => void
  onPeriodChange: (start: string, end: string) => void
}) {
  const [data, setData] = useState<CustomerAnalytics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filterError, setFilterError] = useState<string | null>(null)
  const [filters, setFilters] = useState(initialFilters)
  const [appliedFilters, setAppliedFilters] = useState(initialFilters)
  const [periodPreset, setPeriodPreset] = useState<ReportingPeriodPreset>(
    start || end ? 'custom' : 'last_12_months',
  )
  const [appliedPeriodPreset, setAppliedPeriodPreset] = useState<ReportingPeriodPreset>(
    start || end ? 'custom' : 'last_12_months',
  )
  const [draftStart, setDraftStart] = useState(start)
  const [draftEnd, setDraftEnd] = useState(end)
  const initializedDefaultPeriod = useRef(Boolean(start || end))
  const pendingLocalPeriod = useRef<{ start: string; end: string } | null>(null)
  const defaultPeriod = !start && !end && appliedPeriodPreset !== 'all' && appliedPeriodPreset !== 'custom' && availablePeriod
    ? getReportingPeriod(appliedPeriodPreset, availablePeriod.start, availablePeriod.end, '', '')
    : null
  const queryStart = start || defaultPeriod?.[0] || ''
  const queryEnd = end || defaultPeriod?.[1] || ''
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerRecord | null>(null)
  const [customerDetail, setCustomerDetail] = useState<CustomerDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeTab, setActiveTab] = useState(initialTab ?? 'Overview')

  useEffect(() => {
    if (initialTab) setActiveTab(initialTab)
  }, [initialTab])

  useEffect(() => {
    onTabChange(activeTab)
  }, [activeTab, onTabChange])

  useEffect(() => {
    setDraftStart(start)
    setDraftEnd(end)
    if (pendingLocalPeriod.current?.start === start && pendingLocalPeriod.current.end === end) {
      pendingLocalPeriod.current = null
    } else if (start || end) {
      pendingLocalPeriod.current = null
      setPeriodPreset('custom')
    }
  }, [start, end])

  useEffect(() => {
    if (initializedDefaultPeriod.current || !availablePeriod || start || end) return
    const [periodStart, periodEnd] = getReportingPeriod(
      'last_12_months',
      availablePeriod.start,
      availablePeriod.end,
      '',
      '',
    )
    initializedDefaultPeriod.current = true
    pendingLocalPeriod.current = { start: periodStart, end: periodEnd }
    onPeriodChange(periodStart, periodEnd)
  }, [availablePeriod, end, onPeriodChange, start])

  useEffect(() => {
    if (!start && !end && !availablePeriod && overviewLoading) return
    let active = true
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams()
      if (queryStart) params.set('start', queryStart)
      if (queryEnd) params.set('end', queryEnd)
      if (appliedFilters.year) params.set('year', appliedFilters.year)
      if (appliedFilters.month) params.set('month', appliedFilters.month)
      if (appliedFilters.search.trim()) params.set('search', appliedFilters.search.trim())
      if (appliedFilters.segment) params.set('segment', appliedFilters.segment)
      if (appliedFilters.activity) params.set('activity_status', appliedFilters.activity)
      if (appliedFilters.rfm) params.set('rfm_segment', appliedFilters.rfm)
      if (appliedFilters.minRevenue) params.set('min_revenue', appliedFilters.minRevenue)
      if (appliedFilters.maxRevenue) params.set('max_revenue', appliedFilters.maxRevenue)
      params.set('page', String(appliedFilters.page))
      params.set('page_size', '25')
      setError(null)
      apiGet<CustomerAnalytics>(`/api/analytics/synthetic/customers?${params.toString()}`)
        .then((response) => {
          if (active) setData(response)
        })
        .catch((reason: unknown) => {
          if (active) setError(reason instanceof ApiRequestError ? reason.message : 'Customer analytics could not be loaded.')
        })
    }, appliedFilters.search ? 250 : 0)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [queryStart, queryEnd, appliedFilters, overviewLoading, availablePeriod])

  useEffect(() => {
    if (!selectedCustomer) {
      setCustomerDetail(null)
      return
    }
    let active = true
    setDetailLoading(true)
    setDetailError(null)
    const id = encodeURIComponent(String(selectedCustomer.customer_id))
    const asOf = data?.period.end ? `?as_of=${encodeURIComponent(data.period.end)}` : ''
    apiGet<CustomerDetail>(`/api/analytics/synthetic/customers/${id}${asOf}`)
      .then((response) => { if (active) setCustomerDetail(response) })
      .catch((reason: unknown) => {
        if (active) setDetailError(reason instanceof ApiRequestError ? reason.message : 'Customer detail could not be loaded.')
      })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selectedCustomer, data?.period.end])

  const updateFilter = (key: keyof CustomerFilters, value: string | number) => {
    setFilters((current) => ({ ...current, [key]: value, page: key === 'page' ? Number(value) : 1 }))
    if (key === 'page') {
      setAppliedFilters((current) => ({ ...current, page: Number(value) }))
    }
  }
  const years = useMemo(() => {
    if (!data) return []
    const first = Number(data.available_period.start.slice(0, 4))
    const last = Number(data.available_period.end.slice(0, 4))
    return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) => String(first + index))
  }, [data])
  const segmentChart = data?.segments.map((item) => ({
    name: item.segment,
    value: item.customers,
    color: segmentColors[item.segment],
  })) ?? []
  const revenueChart = data?.segments.map((item) => ({
    name: item.segment === 'No purchase in selected period' ? 'No period purchase' : item.segment,
    value: Number(item.period_net_sales_usd) / 1000,
  })) ?? []
  const averageOrderValueChart = data?.segments
    .filter((item) => item.customers && item.segment !== 'No purchase in selected period')
    .map((item) => ({ name: item.segment, value: Number(item.average_order_value_usd) })) ?? []
  const valueChart = data?.customer_value_distribution.map((item) => ({
    name: `Q${item.value_quintile}`,
    value: item.customers,
  })) ?? []
  const frequencyChart = data?.purchase_frequency_distribution.map((item) => ({
    name: item.order_frequency,
    value: item.customers,
  })) ?? []
  const rfmChart = data?.rfm_segments.map((item) => ({
    name: item.rfm_segment,
    value: item.customers,
  })) ?? []
  const atRiskCount = data?.rfm_segments.find((item) => item.rfm_segment === 'At-risk customers')?.customers ?? 0
  const totalKnown = Number(data?.summary.known_customers ?? 0)
  const inactivityRate = totalKnown
    ? (Number(data?.summary.inactive_customers ?? 0) / totalKnown) * 100
    : 0
  const pageCount = data ? Math.ceil(data.pagination.total / data.pagination.page_size) : 0
  const purchaseHistoryTrend = customerDetail?.purchase_history.slice().reverse() ?? []
  const historyScale = Math.max(
    1,
    ...purchaseHistoryTrend.map((purchase) => Math.abs(Number(purchase.net_sales_usd) || 0)),
  )

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    let [periodStart, periodEnd] = getReportingPeriod(
      periodPreset,
      data?.available_period.start ?? '',
      data?.available_period.end ?? '',
      draftStart,
      draftEnd,
    )
    if (filters.year) {
      const yearStart = `${filters.year}-${filters.month ? filters.month.padStart(2, '0') : '01'}-01`
      const monthNumber = Number(filters.month)
      const finalMonth = monthNumber || 12
      const finalDay = new Date(Number(filters.year), finalMonth, 0).getDate()
      const yearEnd = `${filters.year}-${String(finalMonth).padStart(2, '0')}-${String(finalDay).padStart(2, '0')}`
      periodStart = periodStart ? (periodStart > yearStart ? periodStart : yearStart) : yearStart
      periodEnd = periodEnd ? (periodEnd < yearEnd ? periodEnd : yearEnd) : yearEnd
    }
    if (periodStart && periodEnd && periodStart > periodEnd) {
      setFilterError('The selected date filters do not overlap. Choose a matching year or reporting period.')
      return
    }
    if (periodPreset === 'custom' && (!periodStart || !periodEnd)) {
      setFilterError('Choose both a start and end date for a custom reporting period.')
      return
    }
    setFilterError(null)
    setError(null)
    const nextFilters = { ...filters, page: 1 }
    setFilters(nextFilters)
    setAppliedFilters(nextFilters)
    setAppliedPeriodPreset(periodPreset)
    pendingLocalPeriod.current = { start: periodStart, end: periodEnd }
    onPeriodChange(periodStart, periodEnd)
  }
  const selectSegment = (segment: string) => {
    const nextSegment = filters.segment === segment ? '' : segment
    setFilters((current) => ({ ...current, segment: nextSegment, page: 1 }))
    setAppliedFilters((current) => ({ ...current, segment: nextSegment, page: 1 }))
    document.getElementById('customer-records')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const selectAnalyticsTab = (tab: string, target: string) => {
    setActiveTab(tab)
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return <section className="customer-analytics-page">
    <header className="customer-page-heading">
      <div><div className="panel-kicker">CUSTOMER INTELLIGENCE</div><h1>Customer analytics & retention</h1>
        <p>Understand customer value, purchasing patterns, retention, and observed inactivity.</p></div>
      {data && <div className="customer-period-chip">{data.period.start} — {data.period.end}</div>}
    </header>
    <nav className="domain-tabs" aria-label="Customer Intelligence sections">
      {[
        ['Overview', 'customer-overview'],
        ['Retention', 'customer-retention'],
        ['RFM Analysis', 'customer-rfm'],
        ['Churn Analysis', 'customer-churn'],
      ].map(([tab, target]) => <button key={tab} type="button" className={activeTab === tab ? 'active' : ''} aria-current={activeTab === tab ? 'page' : undefined} onClick={() => selectAnalyticsTab(tab, target)}>{tab}</button>)}
    </nav>

    <form id="customer-overview" className="surface customer-filter-panel" onSubmit={applyFilters}>
      <div className="customer-filter-heading"><div><div className="panel-kicker">REPORTING CONTEXT</div><h2>Customer filters</h2></div>
        <button type="button" className="customer-reset-button" onClick={() => {
          setDraftStart('')
          setDraftEnd('')
          setFilters(initialFilters)
          setAppliedFilters(initialFilters)
          setPeriodPreset('all')
          setAppliedPeriodPreset('all')
          initializedDefaultPeriod.current = true
          pendingLocalPeriod.current = { start: '', end: '' }
          onPeriodChange('', '')
        }}>Reset filters</button>
      </div>
      <div className="customer-filter-grid customer-primary-filters">
        <label><span>Reporting period</span><select value={periodPreset} onChange={(event) => setPeriodPreset(event.target.value as ReportingPeriodPreset)}>
          <option value="last_12_months">Last 12 months</option>
          <option value="last_90_days">Last 90 days</option>
          <option value="year_to_date">Year to date</option>
          <option value="all">All available data</option>
          <option value="custom">Custom date range</option>
        </select></label>
        <label><span>Customer segment</span><select value={filters.segment} onChange={(event) => updateFilter('segment', event.target.value)}><option value="">All segments</option><option>New</option><option>Returning</option><option>No purchase in selected period</option></select></label>
        <label><span>Customer activity</span><select value={filters.activity} onChange={(event) => updateFilter('activity', event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label>
        <label><span>RFM classification</span><select value={filters.rfm} onChange={(event) => updateFilter('rfm', event.target.value)}><option value="">All RFM groups</option>{['Champions', 'Loyal customers', 'Potential loyalists', 'New customers', 'At-risk customers', 'Customers needing attention', 'Hibernating customers', 'Unscored - no purchase history'].map((item) => <option key={item}>{item}</option>)}</select></label>
      </div>
      {periodPreset === 'custom' && <div className="customer-filter-grid customer-custom-period">
        <label><span>From</span><input type="date" required value={draftStart} min={data?.available_period.start} max={data?.available_period.end} onChange={(event) => setDraftStart(event.target.value)}/></label>
        <label><span>To</span><input type="date" required value={draftEnd} min={data?.available_period.start} max={data?.available_period.end} onChange={(event) => setDraftEnd(event.target.value)}/></label>
      </div>}
      <details className="customer-advanced-filters">
        <summary>Advanced filters</summary>
        <div className="customer-filter-grid customer-table-filters">
        <label className="customer-search-field"><span>Search customers</span><input type="search" value={filters.search} placeholder="Customer ID or name" onChange={(event) => updateFilter('search', event.target.value)}/></label>
        <label><span>Year</span><select value={filters.year} onChange={(event) => updateFilter('year', event.target.value)}><option value="">All available years</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        <label><span>Month</span><select value={filters.month} disabled={!filters.year} onChange={(event) => updateFilter('month', event.target.value)}><option value="">All months</option>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={String(index + 1)}>{new Date(2024, index, 1).toLocaleString('en-US', { month: 'long' })}</option>)}</select></label>
        <label><span>Minimum lifetime net sales</span><input type="number" step="0.01" value={filters.minRevenue} onChange={(event) => updateFilter('minRevenue', event.target.value)} placeholder="USD"/></label>
        <label><span>Maximum lifetime net sales</span><input type="number" step="0.01" value={filters.maxRevenue} onChange={(event) => updateFilter('maxRevenue', event.target.value)} placeholder="USD"/></label>
        </div>
      </details>
      <button className="customer-apply-button" type="submit">Use these filter selections</button>
      {filterError && <p className="customer-filter-error" role="alert">{filterError}</p>}
      <p className="customer-filter-hint">Selections apply to customer analytics and records. The reporting period also updates the global reporting period.</p>
    </form>

    {error && <div className="customer-error" role="alert"><strong>Customer analytics unavailable</strong><span>{error}</span><button type="button" onClick={() => setFilters((current) => ({ ...current }))}>Retry</button></div>}
    {!data && !error && <div className="surface customer-loading" role="status">Loading customer aggregates…</div>}
    {data && <>
      <div className="customer-section-heading"><div><div className="panel-kicker">CUSTOMER BASE</div><h2>Key metrics</h2></div><span className="customer-definition-note">Net sales = line revenue less recorded refunds</span></div>
      <div className="customer-metrics-grid">
        <MetricCard label="Total customers" value={number(data.summary.known_customers)} detail={`${number(data.summary.purchasing_customers)} with purchase history`} help="Distinct customer-directory IDs, including customers with no qualifying purchase history. No customer-created date is available for a period comparison."/>
        <MetricCard label="Active customers" value={number(data.summary.active_customers)} detail={`Purchased in the last ${data.inactivity_days} days`} comparison={metricChange(data, 'active_customers')} help={`Observed activity: a qualifying purchase within ${data.inactivity_days} days before the period end. This is not a churn prediction.`}/>
        <MetricCard label="Inactive customers" value={number(data.summary.inactive_customers)} detail={`${inactivityRate.toFixed(1)}% of directory`} comparison={metricChange(data, 'inactive_customers')} help={`No qualifying purchase in the ${data.inactivity_days} days before the selected period end, including customers with no purchase history. This is observed inactivity, not predicted churn.`}/>
        <MetricCard label="Repeat customers" value={number(data.summary.repeat_customers)} detail="Period buyers with 2+ lifetime orders" comparison={metricChange(data, 'repeat_customers')} help="Distinct customers who purchased in this selected period and have at least two qualifying orders through period end."/>
        <MetricCard label="New customers" value={number(data.summary.new_customers)} detail="First qualifying purchase in period" comparison={metricChange(data, 'new_customers')} help="Distinct customers whose first qualifying order date is within the selected inclusive reporting period."/>
        <MetricCard label="One-time customers" value={number(data.summary.one_time_customers)} detail="Exactly one lifetime order" comparison={metricChange(data, 'one_time_customers')} help="Customers with exactly one qualifying order through period end, whether or not that order is inside the selected period."/>
        <MetricCard label="Average lifetime value" value={money(data.summary.average_customer_lifetime_value_usd)} detail="Average historical net sales per known buyer" comparison={metricChange(data, 'average_customer_lifetime_value_usd')} help="Average customer lifetime line revenue less refunds recorded through the selected period end. This is historical value, not predicted future value."/>
        <MetricCard label="Purchase frequency" value={number(data.summary.average_purchase_frequency)} detail="Orders per period buyer" comparison={metricChange(data, 'average_purchase_frequency')} help="Qualifying orders during the selected period divided by distinct customers purchasing in that period."/>
      </div>
      <div className="customer-reconciliation-note">Customer directory: <strong>{number(data.summary.known_customers)}</strong>. Lifetime purchasers: <strong>{number(data.summary.purchasing_customers)}</strong>. Buyers in this reporting period: <strong>{number(data.summary.period_customers)}</strong>, using the same distinct, non-cancelled, line-backed order scope as Executive Overview. Directory totals and period buyers are different populations. The directory total has no period comparison because customer-created dates are unavailable; other comparisons use the preceding equal-length period. A dash means no percentage base is available.</div>

      <div className="customer-section-heading"><div><div className="panel-kicker">SEGMENTATION</div><h2>Who your customers are</h2></div><span className="customer-definition-note">Counts and revenue are reported separately</span></div>
      <div className="customer-chart-grid customer-segmentation-grid">
        <ChartPanel kicker="LIFECYCLE" title="Customer distribution" description="Mutually exclusive groups across the customer directory. No purchase in period includes customers with no purchase history. Select a group to filter records.">
          <div className="customer-donut-layout"><DeferredChart className="customer-donut"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerSegmentDonut data={segmentChart}/></Suspense></DeferredChart>
            <div className="customer-segment-legend">{segmentChart.map((item) => <button key={item.name} className={appliedFilters.segment === item.name ? 'selected' : ''} onClick={() => selectSegment(item.name)}><i style={{ background: item.color }}/><span>{item.name}</span><strong>{number(item.value)}</strong></button>)}</div></div>
        </ChartPanel>
        <ChartPanel kicker="PERIOD REVENUE" title="Revenue contribution by segment" description="Period net sales in USD thousands; not customer counts.">
          <DeferredChart className="customer-chart customer-chart-medium"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={revenueChart} valueLabel="USD thousands"/></Suspense></DeferredChart>
        </ChartPanel>
        <ChartPanel kicker="ORDER VALUE" title="Average order value by segment" description="Period net sales divided by qualifying orders for customers in each group.">
          <DeferredChart className="customer-chart customer-chart-medium"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={averageOrderValueChart} valueLabel="USD per order"/></Suspense></DeferredChart>
        </ChartPanel>
        <ChartPanel kicker="CUSTOMER COUNTS" title="Customers by lifecycle group" description="The groups reconcile to the customer-directory count; no-purchase includes never-purchased customer records.">
          <DeferredChart className="customer-chart customer-chart-medium"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={segmentChart.map(({ name, value }) => ({ name: name === 'No purchase in selected period' ? 'No period purchase' : name, value }))} valueLabel="Customers"/></Suspense></DeferredChart>
        </ChartPanel>
        <ChartPanel kicker="HISTORICAL NET SALES" title="Customer value distribution" description="Lifetime net sales quintiles among customers with purchase history.">
          <DeferredChart className="customer-chart customer-chart-medium"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={valueChart} valueLabel="Customers"/></Suspense></DeferredChart>
          <div className="customer-quintile-footnote">{data.customer_value_distribution.map((item) => <span key={item.value_quintile}>Q{item.value_quintile}: {money(item.minimum_net_sales_usd)}–{money(item.maximum_net_sales_usd)}</span>)}</div>
        </ChartPanel>
      </div>

      <div className="customer-section-heading"><div><div className="panel-kicker">RETENTION & BEHAVIOR</div><h2>Purchasing over time</h2></div></div>
      <div id="customer-retention" className="customer-chart-grid">
        <ChartPanel kicker="COHORT RETENTION" title="Monthly repeat-purchase retention" description="Rows are first-purchase cohorts; each cell is the share with a qualifying order in that month after acquisition.">
          {data.cohorts.length ? <div className="customer-heatmap-wrap"><table className="customer-heatmap"><thead><tr><th>First purchase</th><th>Customers</th>{Array.from({ length: Math.max(0, ...data.cohorts.map((cohort) => cohort.retention.length)) }, (_, index) => <th key={index}>M{index}</th>)}</tr></thead><tbody>
            {data.cohorts.map((cohort) => <tr key={cohort.cohort_month}><th>{cohort.cohort_month}</th><td>{number(cohort.cohort_size)}</td>{cohort.retention.map((cell) => <td key={cell.month_number} title={`Month ${cell.month_number}: ${cell.retained_customers} of ${cohort.cohort_size} customers retained (${cell.retention_pct}%)`} aria-label={`${cell.retained_customers} retained, ${cell.retention_pct}%` } style={{ backgroundColor: `rgba(184, 115, 85, ${0.08 + cell.retention_pct / 125})` }}>{cell.retention_pct.toFixed(1)}%<small>{cell.retained_customers}</small></td>)}</tr>)}
          </tbody></table></div> : <div className="customer-empty">No acquisition cohorts are available in this date range.</div>}
        </ChartPanel>
        <ChartPanel kicker="MONTHLY CUSTOMERS" title="New versus returning customers" description="Distinct purchasers by purchase month; all monthly counts use qualifying orders.">
          <DeferredChart className="customer-chart customer-chart-tall"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerTrendChart data={data.monthly_trend}/></Suspense></DeferredChart>
        </ChartPanel>
        <ChartPanel kicker="ORDER FREQUENCY" title="Purchases per customer" description="Lifetime qualifying order counts through period end.">
          <DeferredChart className="customer-chart customer-chart-medium"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={frequencyChart} valueLabel="Customers"/></Suspense></DeferredChart>
        </ChartPanel>
        <div id="customer-churn"><ChartPanel kicker="OBSERVED ACTIVITY" title="Inactivity and RFM signals" description={`Inactive means no qualifying purchase for ${data.inactivity_days} days as of ${data.period.end}; it is not predicted churn.`}>
          <div className="customer-risk-summary"><div><span>Observed inactive</span><strong>{number(data.summary.inactive_customers)}</strong></div><div><span>Inactivity rate</span><strong>{inactivityRate.toFixed(1)}%</strong></div><div><span>RFM at-risk group</span><strong>{number(atRiskCount)}</strong></div></div>
          <p className="customer-subtle-note">RFM at-risk is a rule-based historical segment, not a prediction. Customer rows include last purchase date and days since purchase.</p>
        </ChartPanel></div>
      </div>

      <div id="customer-rfm" className="customer-section-heading"><div><div className="panel-kicker">RFM CLASSIFICATION</div><h2>Recency, frequency & monetary value</h2></div><span className="customer-definition-note">Heuristic scoring; not machine learning</span></div>
      <ChartPanel kicker="CUSTOMER SEGMENTS" title="RFM distribution" description="Recency, Frequency, and Monetary each use 1–5 quintile scores; 5 is most recent, most frequent, or highest value.">
        <DeferredChart className="customer-chart customer-rfm-chart"><Suspense fallback={<div className="customer-chart-loading" style={{ height: '100%' }}/> }><CustomerBarChart data={rfmChart} valueLabel="Customers" horizontal/></Suspense></DeferredChart>
        <div className="customer-rfm-definitions"><span><strong>Champions:</strong> R≥4, F≥4, M≥4</span><span><strong>Loyal:</strong> R≥3, F≥4</span><span><strong>Potential loyalists:</strong> R≥4, F≥2</span><span><strong>New:</strong> one order, first purchase within 30 days</span><span><strong>At-risk:</strong> R≤2, F≥3</span><span><strong>Needs attention:</strong> R≤2, F≤2</span><span><strong>Hibernating:</strong> remaining purchasing customers</span><span><strong>Unscored:</strong> no purchase history</span></div>
      </ChartPanel>

      <section id="customer-records" className="surface customer-records-panel">
        <div className="customer-panel-heading"><div><div className="panel-kicker">CUSTOMER INVESTIGATION</div><h2>Customer records</h2><p>{number(data.pagination.total)} customers match the current filters. Values are aggregated in PostgreSQL.</p></div></div>
        <div className="customer-table-scroll"><table className="customer-records-table"><thead><tr><th>Customer ID</th><th>Name</th><th>Segment</th><th>First purchase</th><th>Last purchase</th><th>Orders</th><th>Lifetime net sales</th><th>Lifetime avg order value</th><th>Days since purchase</th><th>RFM</th><th>Activity</th></tr></thead><tbody>
          {data.customers.map((customer) => <tr key={customer.customer_id}><td><button className="customer-record-link" onClick={() => setSelectedCustomer(customer)}>{customer.customer_id}</button></td><td>{customer.customer_name || '—'}</td><td>{customer.customer_segment}</td><td>{customer.first_purchase || '—'}</td><td>{customer.last_purchase || '—'}</td><td>{number(customer.total_orders)}</td><td>{money(customer.lifetime_net_sales_usd)}</td><td>{money(customer.average_order_value_usd)}</td><td>{customer.days_since_last_purchase === null ? '—' : number(customer.days_since_last_purchase)}</td><td><span className="customer-rfm-badge">{customer.rfm_segment}</span></td><td><span className={`customer-status ${customer.activity_status}`}>{customer.activity_status}</span></td></tr>)}
          {!data.customers.length && <tr><td colSpan={11} className="customer-empty">No customers match the current filters.</td></tr>}
        </tbody></table></div>
        <div className="customer-pagination"><span>Page {data.pagination.page} of {Math.max(pageCount, 1)}</span><div><button disabled={data.pagination.page <= 1} onClick={() => updateFilter('page', data.pagination.page - 1)}>Previous</button><button disabled={data.pagination.page >= pageCount} onClick={() => updateFilter('page', data.pagination.page + 1)}>Next</button></div></div>
      </section>
    </>}

    {selectedCustomer && <div className="customer-detail-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedCustomer(null) }}>
      <aside className="customer-detail-panel" role="dialog" aria-modal="true" aria-label="Customer details">
        <div className="customer-detail-header"><div><div className="panel-kicker">CUSTOMER DETAIL</div><h2>{customerDetail?.customer.customer_name || `Customer ${selectedCustomer.customer_id}`}</h2><span>ID {selectedCustomer.customer_id}</span></div><button onClick={() => setSelectedCustomer(null)} aria-label="Close customer details">×</button></div>
        {detailLoading && <div className="customer-loading">Loading customer aggregates…</div>}
        {detailError && <div className="customer-error" role="alert">{detailError}</div>}
        {customerDetail && <>
          <div className="customer-detail-metrics"><div><span>Lifetime net sales</span><strong>{money(customerDetail.customer.net_sales_usd)}</strong></div><div><span>Total orders</span><strong>{number(customerDetail.customer.total_orders)}</strong></div><div><span>Last purchase</span><strong>{customerDetail.customer.last_purchase || '—'}</strong></div><div><span>Days since</span><strong>{customerDetail.customer.days_since_last_purchase === null ? '—' : number(customerDetail.customer.days_since_last_purchase)}</strong></div></div>
          <div className="customer-detail-classification">
            <div><strong>Lifecycle: {selectedCustomer.customer_segment}</strong><p>{customerSegmentExplanation(selectedCustomer.customer_segment)}</p></div>
            <div><strong>RFM: {selectedCustomer.rfm_segment}</strong><p>{rfmSegmentExplanation(selectedCustomer.rfm_segment)}</p>
              {selectedCustomer.recency_score !== null && <small>Scores · R {selectedCustomer.recency_score} / F {selectedCustomer.frequency_score} / M {selectedCustomer.monetary_score}</small>}
            </div>
          </div>
          <div className="customer-detail-section"><h3>Revenue trend · most recent {purchaseHistoryTrend.length} orders</h3>
            {purchaseHistoryTrend.length ? <div className="customer-history-chart"><svg viewBox="0 0 360 92" role="img" aria-label="Net sales by recent order, in chronological order"><line x1="0" x2="360" y1="46" y2="46"/>{purchaseHistoryTrend.map((purchase, index) => {
              const amount = Number(purchase.net_sales_usd) || 0
              const barHeight = Math.abs(amount) / historyScale * 36
              const step = 360 / purchaseHistoryTrend.length
              return <rect key={purchase.order_id} x={index * step + step * 0.15} y={amount >= 0 ? 46 - barHeight : 46} width={Math.max(2, step * 0.7)} height={Math.max(1, barHeight)}><title>{purchase.order_date}: {money(purchase.net_sales_usd)}</title></rect>
            })}</svg></div> : <p className="customer-subtle-note">No qualifying purchase history is available for this customer.</p>}
          </div>
          <div className="customer-detail-section"><h3>Recent purchase history</h3><div className="customer-history-list">{customerDetail.purchase_history.map((purchase) => <div key={purchase.order_id}><span>{purchase.order_date}<small>{purchase.product_count} products</small></span><strong>{money(purchase.net_sales_usd)}</strong></div>)}</div></div>
          <div className="customer-detail-section"><h3>Top product preferences</h3>{customerDetail.product_preferences.length ? <div className="customer-history-list">{customerDetail.product_preferences.map((product) => <div key={product.product_id}><span>{product.product_name}<small>{product.category} · {product.order_count} orders</small></span><strong>{money(product.gross_sales_usd)}</strong></div>)}</div> : <p className="customer-subtle-note">No product preference data is available.</p>}</div>
          <p className="customer-subtle-note">Only recorded customer and purchase data is shown. No additional personal details are inferred.</p>
        </>}
      </aside>
    </div>}
  </section>
}

export default CustomerAnalyticsDashboard
