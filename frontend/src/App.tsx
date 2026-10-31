import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { apiGet, ApiRequestError } from './services/api'
import { BrandIcon, BrandLogo } from './components/BrandLogo'
import { ReportingPeriodFilter, type PeriodComparison, type ReportingGranularity } from './components/ReportingPeriodFilter'
import { BusinessPulse, WhatIfSimulator } from './components/BusinessPulse'
import { DecisionImpactTracker } from './components/DecisionImpactTracker'
const CustomerAnalyticsDashboard = lazy(() => import('./components/CustomerAnalyticsDashboard'))
type ActionItem = { id: string; priority: 'High' | 'Medium' | 'Low'; title: string; entity: string; impact: number; owner: string; due: string; status: 'Needs review' | 'Draft'; evidence: string; assumption: string }
type Insight = { id: string; kind: string; severity: 'Opportunity' | 'Review' | 'Watch'; title: string; evidence: string; impact: string; assumption: string; action: string }

type ApiState = 'checking' | 'connected' | 'offline'
type NavItem = { label: string; icon: string }
type SavedView = {
  id: string
  name: string
  section: string
  tab: string | null
  start: string
  end: string
  granularity: ReportingGranularity
  comparison: PeriodComparison
  savedAt: string
}
type Metric = { label: string; value: string; change: string | null; direction: 'up' | 'down'; points: number[]; definition: string }
type TrendPoint = { period: string; revenue: number; profit: number; margin: number; orders: number }
type LiveCategory = { name: string; share: number; color: string }
type SyntheticOverview = {
  dataset: string
  synthetic: boolean
  sales_policy: string
  return_policy: string
  reporting_period: { start: string; end: string }
  available_period: { start: string; end: string }
  granularity: ReportingGranularity
  gross_sales_usd: string
  gross_profit_before_returns_usd: string
  refunds_usd: string
  order_count: number
  has_sales_records: boolean
  customer_count: number
  repeat_customer_count: number
  inactive_customer_count: number
  churn_rule: string
  customer_segments: { segment: string; customers: number }[]
  latest_inventory_snapshot: string | null
  latest_inventory_value_usd: string
  low_stock_count: number
  trend: { period: string; gross_sales_usd: string; gross_profit_before_returns_usd: string; order_count: number }[]
  daily_sales: { date: string; gross_sales_usd: string; gross_profit_usd: string; order_count: number }[]
  weekday_sales: { weekday: number; weekday_name: string; gross_sales_usd: string; order_count: number }[]
  highlights: Record<string, {
    month?: string
    period?: string
    date?: string
    weekday_name?: string
    category?: string
    gross_sales_usd?: string
    gross_profit_usd?: string
    order_count?: number
    average_daily_revenue_usd?: string
    change_vs_average_usd?: string
  } | null>
  comparison: {
    type: PeriodComparison
    start: string | null
    end: string | null
    has_data: boolean
    gross_sales_change_usd: string | null
    gross_sales_change_pct: string | null
    gross_profit_change_usd: string | null
    gross_profit_change_pct: string | null
    order_count_change: number | null
    order_count_change_pct: string | null
  }
  monthly: { month: string; gross_sales_usd: string; gross_profit_before_returns_usd: string }[]
  categories: { category: string; gross_sales_usd: string }[]
  category_drivers: {
    category: string
    gross_sales_usd: string
    contribution_pct: string
    best_month: string
    best_month_gross_sales_usd: string
  }[]
  top_products: { product_id: string; product_name: string; category: string; revenue_usd: string }[]
  actions: ActionItem[]
}

const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
const monthLabel = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
const quarterLabel = (value: string) => {
  const date = new Date(`${value}T00:00:00Z`)
  return `Q${Math.floor(date.getUTCMonth() / 3) + 1} ${date.getUTCFullYear()}`
}
const categoryColors = ['#b87355', '#4b4b45', '#aa9b86', '#d9d2c8', '#5d625b']

const navGroups: { title: string; items: NavItem[] }[] = [
  { title: 'Business domains', items: [
    { label: 'Executive Overview', icon: 'overview' }, { label: 'Customer Intelligence', icon: 'customers' },
    { label: 'Sales & Revenue', icon: 'sales' }, { label: 'Financial Performance', icon: 'finance' },
    { label: 'Inventory & Supply Chain', icon: 'inventory' },
  ] },
  { title: 'Workspace', items: [
    { label: 'Decision Center', icon: 'decision' }, { label: 'Reports & BI', icon: 'reports' },
    { label: 'Data Management', icon: 'data' }, { label: 'Saved Views', icon: 'bookmark' },
    { label: 'Settings', icon: 'settings' },
  ] },
]
const SAVED_VIEWS_STORAGE_KEY = 'biznexa.savedViews'

function readSavedViews(): SavedView[] {
  try {
    const stored = window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)
    if (!stored) return []
    const parsed: unknown = JSON.parse(stored)
    if (!Array.isArray(parsed)) throw new Error('Saved views data must be a list.')
    return parsed.filter((view): view is SavedView =>
      typeof view === 'object' && view !== null &&
      typeof view.id === 'string' && typeof view.name === 'string' &&
      typeof view.section === 'string' &&
      (view.tab === null || typeof view.tab === 'string') &&
      typeof view.start === 'string' && typeof view.end === 'string' &&
      typeof view.granularity === 'string' && typeof view.comparison === 'string' &&
      typeof view.savedAt === 'string',
    )
  } catch (error) {
    console.error('Could not read saved views from browser storage.', error)
    return []
  }
}

const RevenueChart = lazy(() => import('./components/AnalyticsCharts').then((module) => ({ default: module.RevenueChart })))
const CategoryDonut = lazy(() => import('./components/AnalyticsCharts').then((module) => ({ default: module.CategoryDonut })))

function Icon({ name, size = 17 }: { name: string; size?: number }) {
  const icons: Record<string, ReactNode> = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    customers: <><circle cx="9" cy="8" r="3.5"/><path d="M2.8 20v-1.5a5.5 5.5 0 0 1 11 0V20M16 5.2a3.5 3.5 0 0 1 0 6.8M17.4 15a4.8 4.8 0 0 1 3.8 4.7"/></>,
    sales: <><path d="M3 20h18M5 16l4-5 3 2 7-8"/><path d="M15 5h4v4"/></>,
    finance: <><path d="M4 20V9m5 11V4m5 16v-7m5 7V7"/><path d="M2 20h20"/></>,
    inventory: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v9l9 5 9-5V8M12 13v9"/></>,
    suppliers: <><path d="M3 6h12v12H3z"/><path d="M15 10h4l3 3v5h-7"/><circle cx="7.5" cy="19" r="1.5"/><circle cx="18.5" cy="19" r="1.5"/></>,
    predict: <><path d="M12 3a7 7 0 0 0-4.2 12.6c.8.6 1.2 1.4 1.2 2.4h6c0-1 .4-1.8 1.2-2.4A7 7 0 0 0 12 3Z"/><path d="M9.5 21h5M10 18h4M12 6v2m4 2-1.5 1M8 10l1.5 1"/></>,
    decision: <><path d="M12 3v5m0 0 4-3m-4 3L8 5M6 13a6 6 0 1 0 12 0M6 13H3m15 0h3M12 19v2"/><circle cx="12" cy="13" r="2"/></>,
    reports: <><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7m-7 4h7"/></>,
    data: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
    bookmark: <><path d="M6 4h12v17l-6-4-6 4z"/></>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.7 10.7 6.6-4.4m-6.6 7 6.6 4.4"/></>,
    star: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.7 1l-.3 1.9h-2.7l-.3-1.9a8 8 0 0 1-1.8-.7l-1.6.9-1.9-1.9.9-1.6a8 8 0 0 1-.7-1.8L5.8 14v-2.7l1.9-.3a8 8 0 0 1 .7-1.8l-.9-1.6 1.9-1.9 1.6.9a8 8 0 0 1 1.8-.7L13.1 4h2.7l.3 1.9a8 8 0 0 1 1.8.7l1.6-.9 1.9 1.9-.9 1.6a8 8 0 0 1 .7 1.8l1.9.3V14l-1.9.3a8 8 0 0 1-.7 1.8Z"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
    chevron: <path d="m7 10 5 5 5-5"/>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    arrow: <><path d="M7 17 17 7M7 7h10v10"/></>,
    sliders: <><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="currentColor"/><circle cx="15" cy="12" r="2" fill="currentColor"/><circle cx="10" cy="18" r="2" fill="currentColor"/></>,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/></>,
    arrowRight: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    box: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v9l9 5 9-5V8"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  }
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">{icons[name] ?? icons.overview}</svg>
}

function Sparkline({ points, direction }: { points: number[]; direction: 'up' | 'down' }) {
  const safePoints = points.filter(Number.isFinite)
  const renderedPoints = safePoints.length > 0 ? safePoints : [0]
  const max = Math.max(...renderedPoints)
  const min = Math.min(...renderedPoints)
  const denominator = Math.max(renderedPoints.length - 1, 1)
  const path = renderedPoints.map((point, index) => {
    const x = (index / denominator) * 68
    const y = 21 - ((point - min) / Math.max(max - min, 1)) * 17
    return `${index ? 'L' : 'M'}${x} ${y}`
  }).join(' ')
  return <svg aria-hidden="true" className={`sparkline ${direction}`} viewBox="0 0 68 24"><path d={path}/></svg>
}

function KpiCard({ metric, compareLabel, index }: { metric: Metric; compareLabel: string; index: number }) {
  const signedChange = metric.change !== null && /^[+-]/.test(metric.change)
  return <article className={`kpi-card kpi-${index}`} title={metric.definition}>
    <div className="kpi-card-heading"><span>{metric.label}</span><button className="definition-tip" aria-label={`Definition: ${metric.label}`} title={metric.definition}><Icon name="info" size={14}/></button></div>
    <div className="kpi-main"><strong>{metric.value}</strong><Sparkline points={metric.points} direction={metric.direction}/></div>
    <div className="kpi-comparison"><span className={`movement ${metric.change ? metric.direction : 'neutral'}`}>{metric.change && !signedChange && <span aria-hidden="true">{metric.direction === 'up' ? '+' : '-'}</span>} {metric.change ?? '—'}</span>{compareLabel && <span className="comparison-context">{compareLabel}</span>}</div>
  </article>
}

function KpiSkeleton() {
  return <article className="kpi-card skeleton-card" aria-hidden="true">
    <span className="skeleton-block skeleton-label"/>
    <span className="skeleton-block skeleton-value"/>
    <span className="skeleton-block skeleton-meta"/>
  </article>
}

function App() {
  const [apiState, setApiState] = useState<ApiState>('checking')
  const [activeSection, setActiveSection] = useState('Executive Overview')
  const [requestedDomainTab, setRequestedDomainTab] = useState<string | null>(null)
  const [activeDomainTab, setActiveDomainTab] = useState<string | null>(null)
  const [savedViews, setSavedViews] = useState<SavedView[]>(readSavedViews)
  const [savedViewsError, setSavedViewsError] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [notificationOpen, setNotificationOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [selectedAction, setSelectedAction] = useState<ActionItem | null>(null)
  const [selectedInsight, setSelectedInsight] = useState<Insight | null>(null)
  const [reviewedActions, setReviewedActions] = useState<string[]>([])
  const [syntheticOverview, setSyntheticOverview] = useState<SyntheticOverview | null>(null)
  const [availablePeriod, setAvailablePeriod] = useState<{ start: string; end: string } | null>(null)
  const [dataError, setDataError] = useState<string | null>(null)
  const [dataLoading, setDataLoading] = useState(true)
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [granularity, setGranularity] = useState<ReportingGranularity>('month')
  const [comparison, setComparison] = useState<PeriodComparison>('previous_period')
  const requestId = useRef(0)

  useEffect(() => {
    try {
      window.localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, JSON.stringify(savedViews))
      setSavedViewsError(null)
    } catch (error) {
      console.error('Could not save views to browser storage.', error)
      setSavedViewsError('Saved views could not be stored in this browser.')
    }
  }, [savedViews])

  useEffect(() => {
    let mounted = true
    const currentRequestId = ++requestId.current
    const params = new URLSearchParams({
      granularity,
      comparison,
      include_daily_sales: 'false',
    })
    if (rangeStart) params.set('start', rangeStart)
    if (rangeEnd) params.set('end', rangeEnd)
    setDataLoading(true)
    setSyntheticOverview(null)
    setDataError(null)
    apiGet<SyntheticOverview>(`/api/analytics/synthetic/overview?${params.toString()}`)
      .then((data) => {
        if (mounted && currentRequestId === requestId.current && data.synthetic) {
          setSyntheticOverview(data)
          setAvailablePeriod(data.available_period)
          setDataError(null)
          setApiState('connected')
        }
      })
      .catch((reason: unknown) => {
        if (mounted && currentRequestId === requestId.current) {
          setSyntheticOverview(null)
          setDataError(reason instanceof ApiRequestError ? reason.message : 'The analytics query was not available.')
          apiGet<{ status: string }>('/health')
            .then((health) => {
              if (mounted && currentRequestId === requestId.current) {
                setApiState(health.status === 'ok' ? 'connected' : 'offline')
              }
            })
            .catch(() => {
              if (mounted && currentRequestId === requestId.current) setApiState('offline')
            })
        }
      })
      .finally(() => { if (mounted && currentRequestId === requestId.current) setDataLoading(false) })
    return () => { mounted = false }
  }, [rangeStart, rangeEnd, granularity, comparison])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setSelectedAction(null); setSelectedInsight(null); setSearchOpen(false); setNotificationOpen(false); setProfileOpen(false); setMobileNavOpen(false) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const periodLabel = syntheticOverview?.reporting_period
    ? `${syntheticOverview.reporting_period.start} – ${syntheticOverview.reporting_period.end}`
    : 'Validated dataset'
  const trend: TrendPoint[] = syntheticOverview?.trend.map((row) => {
    const revenue = Number(row.gross_sales_usd) / 1_000_000
    const profit = Number(row.gross_profit_before_returns_usd) / 1_000_000
    const period = granularity === 'day' ? row.period.slice(5) : granularity === 'week' ? row.period : granularity === 'month' ? row.period.slice(0, 7) : row.period
    return { period, revenue, profit, margin: revenue ? (profit / revenue) * 100 : 0, orders: row.order_count }
  }) ?? []
  const liveCategories: LiveCategory[] = useMemo(() => {
    const total = syntheticOverview?.categories.reduce((sum, row) => sum + Number(row.gross_sales_usd), 0) ?? 0
    return syntheticOverview?.categories.map((row, index) => ({
      name: row.category,
      share: total ? Number(((Number(row.gross_sales_usd) / total) * 100).toFixed(1)) : 0,
      color: categoryColors[index % categoryColors.length],
    })) ?? []
  }, [syntheticOverview])
  const salesChange = syntheticOverview?.comparison.gross_sales_change_pct
  const profitChange = syntheticOverview?.comparison.gross_profit_change_pct
  const liveMetrics: Metric[] = syntheticOverview ? [
    ...(syntheticOverview.has_sales_records ? [
      { label: 'Gross sales', value: money(Number(syntheticOverview.gross_sales_usd)), change: salesChange === null || salesChange === undefined ? null : `${Number(salesChange) >= 0 ? '+' : ''}${Number(salesChange).toFixed(1)}%`, direction: salesChange && Number(salesChange) < 0 ? 'down' as const : 'up' as const, points: trend.map((item) => item.revenue), definition: 'Sum of line revenue for non-cancelled orders. Returns are reported separately.' },
      { label: 'Gross profit', value: money(Number(syntheticOverview.gross_profit_before_returns_usd)), change: profitChange === null || profitChange === undefined ? null : `${Number(profitChange) >= 0 ? '+' : ''}${Number(profitChange).toFixed(1)}%`, direction: profitChange && Number(profitChange) < 0 ? 'down' as const : 'up' as const, points: trend.map((item) => item.profit), definition: 'Gross sales less sale-time COGS before return adjustments.' },
      { label: 'Orders', value: syntheticOverview.order_count.toLocaleString(), change: syntheticOverview.comparison.order_count_change_pct === null ? null : `${Number(syntheticOverview.comparison.order_count_change_pct) >= 0 ? '+' : ''}${Number(syntheticOverview.comparison.order_count_change_pct).toFixed(1)}%`, direction: syntheticOverview.comparison.order_count_change_pct && Number(syntheticOverview.comparison.order_count_change_pct) < 0 ? 'down' as const : 'up' as const, points: trend.map((item) => item.orders), definition: 'Distinct non-cancelled orders in the selected reporting period.' },
    ] : []),
    { label: 'Latest inventory', value: money(Number(syntheticOverview.latest_inventory_value_usd)), change: syntheticOverview.latest_inventory_snapshot ? `Snapshot ${syntheticOverview.latest_inventory_snapshot}` : 'No snapshot', direction: 'up', points: [Number(syntheticOverview.latest_inventory_value_usd)], definition: 'Point-in-time inventory value from the latest validated snapshot; it is not summed over time.' },
  ] : []
  const compareLabel = syntheticOverview?.comparison.has_data
    ? syntheticOverview.comparison.type === 'same_period_last_year' ? 'vs previous year' : 'vs previous period'
    : ''
  const comparisonNotice = syntheticOverview?.has_sales_records && !syntheticOverview.comparison.has_data
    ? comparison === 'none'
      ? 'No comparison selected; KPI changes are unavailable.'
      : 'Comparison period has no records; KPI changes are unavailable.'
    : null
  const period = { label: periodLabel, compareLabel, metrics: liveMetrics, trend }
  const categories = liveCategories
  const products: { sku: string; name: string; category: string; revenue: Record<string, number>; growth: number | null }[] = syntheticOverview?.top_products.map((product) => ({ sku: product.product_id, name: product.product_name, category: product.category, revenue: { year: Number(product.revenue_usd) }, growth: null })) ?? []
  const insights: Insight[] = []
  const periodId = 'year'
  const searchResults: { title: string; type: string; section: string }[] = []
  const [priorityFilter, setPriorityFilter] = useState('All priorities')
  const [impactOrder, setImpactOrder] = useState<'high' | 'low'>('high')
  const filteredActions: ActionItem[] = syntheticOverview?.actions.filter((action) => priorityFilter === 'All priorities' || action.priority === priorityFilter).sort((a, b) => impactOrder === 'high' ? b.impact - a.impact : a.impact - b.impact) ?? []
  const riskSegments = syntheticOverview?.customer_segments.map((segment) => ({ ...segment, share: syntheticOverview.customer_count ? Math.round((segment.customers / syntheticOverview.customer_count) * 1000) / 10 : 0 })) ?? []
  const isOverview = activeSection === 'Executive Overview'

  const goTo = (requestedSection: string, tab: string | null = null) => {
    const section = requestedSection === 'Supplier Intelligence'
      ? 'Inventory & Supply Chain'
      : requestedSection === 'Predictive Analytics'
        ? 'Customer Intelligence'
        : requestedSection
    const domainTab = requestedSection === 'Supplier Intelligence'
      ? 'Supplier Performance'
      : requestedSection === 'Predictive Analytics'
        ? 'Churn Analysis'
        : tab
    setActiveSection(section)
    setRequestedDomainTab(domainTab)
    setActiveDomainTab(domainTab)
    setSearchOpen(false)
    setSearch('')
    setNotificationOpen(false)
    setMobileNavOpen(false)
  }
  const updatePeriodFilters = (filters: {
    start: string
    end: string
    granularity: ReportingGranularity
    comparison: PeriodComparison
  }) => {
    setRangeStart(filters.start)
    setRangeEnd(filters.end)
    setGranularity(filters.granularity)
    setComparison(filters.comparison)
  }
  const resetPeriodFilters = () => {
    setRangeStart('')
    setRangeEnd('')
    setGranularity('month')
    setComparison('previous_period')
  }
  const handleSearchResult = (section: string) => goTo(section)
  const closeDrawer = () => { setSelectedAction(null); setSelectedInsight(null) }
  const saveCurrentView = () => {
    const name = activeDomainTab ? `${activeSection} · ${activeDomainTab}` : activeSection
    const savedView: SavedView = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      section: activeSection,
      tab: activeDomainTab,
      start: rangeStart,
      end: rangeEnd,
      granularity,
      comparison,
      savedAt: new Date().toISOString(),
    }
    setSavedViews((current) => [savedView, ...current])
  }
  const openSavedView = (savedView: SavedView) => {
    setRangeStart(savedView.start)
    setRangeEnd(savedView.end)
    setGranularity(savedView.granularity)
    setComparison(savedView.comparison)
    goTo(savedView.section, savedView.tab)
  }

  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''} ${mobileNavOpen ? 'mobile-nav-open' : ''}`}>
    <aside className="sidebar">
      <div className="brand-row">
        <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); goTo('Executive Overview') }} aria-label="BizNexa executive overview">
          <BrandLogo className="brand-full" />
          <BrandIcon className="brand-compact" variant="dark" alt="BizNexa bee and honeycomb icon" />
        </a>
        <button className="collapse-button" aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} aria-expanded={!collapsed} title={collapsed ? 'Expand navigation' : 'Collapse navigation'} onClick={() => setCollapsed((value) => !value)}><span>{collapsed ? '>' : '<'}</span></button>
      </div>
      <div className="workspace-switcher" title="Business workspace">
        <span className="workspace-avatar">B</span><span className="workspace-copy"><strong>Business workspace</strong><small>Single organization</small></span><Icon name="chevron" size={14}/>
      </div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {navGroups.map((group) => <div className="nav-group" key={group.title}>
          <div className="nav-group-label">{group.title}</div>
          {group.items.map((item) => <button key={item.label} title={collapsed ? item.label : undefined} className={`nav-item ${activeSection === item.label ? 'active' : ''}`} onClick={() => goTo(item.label)} aria-current={activeSection === item.label ? 'page' : undefined}>
            <Icon name={item.icon}/><span className="nav-item-label">{item.label}</span>{item.label === 'Decision Center' && !collapsed && <span className="nav-badge">3</span>}
          </button>)}
        </div>)}
      </nav>
      <div className="sidebar-foot">
        <div className="sidebar-system"><span className={`system-indicator ${apiState}`}/><span className="system-copy">{apiState === 'connected' ? 'API connected' : apiState === 'checking' ? 'Checking service' : 'API unavailable'}</span><span className="system-help" title="This checks the BizNexa API only. Business data connection status is shown separately.">i</span></div>
        <button className="profile-row" onClick={() => setProfileOpen(!profileOpen)} aria-expanded={profileOpen}>
          <span className="profile-avatar">BA</span><span className="profile-copy"><strong>Workspace admin</strong><small>Administrator</small></span><Icon name="more" size={18}/>
        </button>
        {profileOpen && <div className="profile-menu"><strong>Workspace admin</strong><span>Local preview profile</span><button onClick={() => { setProfileOpen(false); goTo('Settings') }}>Workspace settings</button></div>}
      </div>
    </aside>
    {mobileNavOpen && <button className="sidebar-overlay" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}/>}

    <main className="main-content">
      <header className="topbar">
        <button className="mobile-menu-button" aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((value) => !value)}><Icon name={mobileNavOpen ? 'close' : 'menu'} size={19}/></button>
        <div className="topbar-title"><span className="topbar-section"><BrandIcon size="header" variant="light" alt=""/><span>BizNexa</span></span><span className="crumb-slash">/</span><span>{activeSection}</span></div>
        <div className="topbar-controls">
          {!['Saved Views', 'Settings', 'Data Management'].includes(activeSection) && <button className="save-view-button" onClick={saveCurrentView} title="Bookmark this dashboard with its current reporting filters"><Icon name="bookmark" size={14}/><span>Save view</span></button>}
          <div className="search-wrap">
            <Icon name="search" size={16}/><input value={search} onChange={(event) => { setSearch(event.target.value); setSearchOpen(true) }} onFocus={() => setSearchOpen(true)} onKeyDown={(event) => { if (event.key === 'Escape') setSearchOpen(false) }} placeholder="Search insights, products..." aria-label="Search products, insights, and reports"/>
            <kbd>Ctrl K</kbd>
            {searchOpen && <div className="search-popover"><div className="popover-label">{search ? 'SEARCH RESULTS' : 'SUGGESTED'}</div>{searchResults.length ? searchResults.map((result) => <button key={result.title} className="search-result" onClick={() => handleSearchResult(result.section)}><span className="result-icon"><Icon name={result.type === 'Product' ? 'inventory' : result.type === 'Insight' ? 'decision' : 'reports'} size={15}/></span><span><strong>{result.title}</strong><small>{result.type} - {result.section}</small></span><Icon name="arrowRight" size={14}/></button>) : <div className="no-search-results">No validated records found.</div>}<div className="search-footnote">Search will use validated records when entity endpoints are available.</div></div>}
          </div>
          <div className="period-control"><Icon name="calendar" size={15}/><span>{period.label}</span></div>
          <button className={`top-icon-button ${notificationOpen ? 'pressed' : ''}`} aria-label="Open insights notifications" aria-expanded={notificationOpen} onClick={() => { setNotificationOpen(!notificationOpen); setProfileOpen(false) }}><Icon name="bell" size={17}/><span className="notification-dot"/></button>
          <button className="top-user" onClick={() => { setProfileOpen(!profileOpen); setNotificationOpen(false) }} aria-label="Open profile menu">BA</button>
        </div>
      </header>
      {(searchOpen || profileOpen) && <button className="dismiss-layer" aria-label="Close open menu" onClick={() => { setSearchOpen(false); setProfileOpen(false) }}/>}

      <div className="page-content">
        {!isOverview ? activeSection === 'Customer Intelligence'
          ? <Suspense fallback={<div className="surface customer-loading" role="status">Loading customer analytics…</div>}>
            <CustomerAnalyticsDashboard
              start={rangeStart}
              end={rangeEnd}
              availablePeriod={availablePeriod}
              overviewLoading={dataLoading}
              initialTab={requestedDomainTab}
              onTabChange={setActiveDomainTab}
              onPeriodChange={(start, end) => { setRangeStart(start); setRangeEnd(end) }}
            />
          </Suspense>
          : <AnalyticsModule
            section={activeSection}
            initialTab={requestedDomainTab}
            onBack={() => goTo('Executive Overview')}
            onNavigate={goTo}
            onTabChange={setActiveDomainTab}
            start={rangeStart}
            end={rangeEnd}
            granularity={granularity}
            overview={syntheticOverview}
            apiState={apiState}
            savedViews={savedViews}
            savedViewsError={savedViewsError}
            onOpenSavedView={openSavedView}
            onDeleteSavedView={(id) => setSavedViews((current) => current.filter((view) => view.id !== id))}
          /> : <>
          <div className={`demo-banner ${syntheticOverview ? 'live-banner' : ''}`}><span className="demo-mark">{dataLoading ? '…' : syntheticOverview ? 'OK' : '!'}</span><span><strong>{dataLoading ? 'Loading analytics' : syntheticOverview ? (syntheticOverview.synthetic ? 'Validated synthetic dataset' : 'Connected business dataset') : dataError ? 'Data connection unavailable' : 'Backend data unavailable'}</strong><i/> {dataLoading ? 'Querying the selected date range…' : syntheticOverview ? 'Metrics are loaded from the configured Supabase schema.' : dataError ?? 'Start the API and initialize the Supabase data schema to view live metrics.'}</span><span className="demo-period">USD <i/> {period.label}</span></div>

          <section className="overview-hero">
            <h1 className="visually-hidden">Executive overview</h1>
            <ReportingPeriodFilter
              start={rangeStart}
              end={rangeEnd}
              availableStart={availablePeriod?.start ?? ''}
              availableEnd={availablePeriod?.end ?? ''}
              granularity={granularity}
              comparison={comparison}
              onApply={updatePeriodFilters}
              onReset={resetPeriodFilters}
            />
          </section>

          <section className="kpi-grid" aria-label="Executive key performance indicators" aria-busy={dataLoading}>
            {!dataLoading && syntheticOverview && !syntheticOverview.has_sales_records && <div className="data-empty">No sales records exist in this date range; sales KPIs and highlights are withheld.</div>}
            {dataLoading
              ? Array.from({ length: 4 }, (_, index) => <KpiSkeleton key={index}/>)
              : period.metrics.length
                ? period.metrics.map((metric, index) => <KpiCard key={metric.label} metric={metric} compareLabel={period.compareLabel} index={index}/>)
                : <div className="data-empty">No KPI values are available.</div>}
            {!dataLoading && comparisonNotice && <div className="comparison-note" role="note">{comparisonNotice}</div>}
          </section>

          <section className="primary-grid">
            <article className="surface revenue-panel">
              <div className="panel-header"><div><div className="panel-kicker">PERFORMANCE</div><h2>Revenue & profitability</h2><p>{granularity[0].toUpperCase() + granularity.slice(1)} performance · {period.compareLabel}</p></div><button className="quiet-link" onClick={() => goTo('Sales & Revenue')}>Explore sales <Icon name="arrow" size={13}/></button></div>
              {dataLoading ? <div className="chart-skeleton" role="status" aria-label="Loading revenue and profitability chart"><span/><span/><span/><span/><span/><span/><span/><span/></div> : period.trend.length ? <Suspense fallback={<div className="chart-skeleton" role="status" aria-label="Loading revenue and profitability chart"><span/><span/><span/><span/><span/><span/><span/><span/></div>}><RevenueChart data={period.trend}/></Suspense> : <div className="chart-loading">No sales rows exist for this date range.</div>}
              <div className="chart-footnote"><Icon name="info" size={13}/> Revenue and gross profit in USD millions - Margin uses a separate percentage axis</div>
            </article>

            <aside className="insights-panel">
              <div className="insights-head"><div><div className="panel-kicker copper-kicker">BIZNEXA INSIGHTS</div><h2>Signals to explore</h2><p>No validated recommendations are available yet.</p></div></div>
              <div className="insight-list">{insights.map((insight, index) => <button className="insight-card" key={insight.id} onClick={() => setSelectedInsight(insight)}>
                <div className="insight-meta"><span className={`insight-type insight-${index}`}>{insight.kind}</span><span className="insight-severity">{insight.severity}</span></div>
                <strong>{insight.title}</strong><p>{insight.evidence}</p><span className="insight-impact">{insight.impact}</span>
              </button>)}</div>
              <button className="insights-footer" onClick={() => goTo('Decision Center')}>View all insights <Icon name="arrowRight" size={14}/></button>
            </aside>
          </section>

          <section className="surface performance-highlights">
            <div className="panel-header"><div><div className="panel-kicker">MEASURED FROM SELECTED RECORDS</div><h2>Business Performance Highlights</h2><p>Period highs and patterns calculated from non-cancelled order lines.</p></div></div>
            {dataLoading
              ? <div className="highlights-grid skeleton-highlights" role="status" aria-label="Loading business performance highlights">{Array.from({ length: 4 }, (_, index) => <div className="highlight-item" key={index}><span className="skeleton-block"/><strong className="skeleton-block"/><small className="skeleton-block"/></div>)}</div>
              : syntheticOverview && !syntheticOverview.has_sales_records
              ? <div className="empty-state"><strong>No sales records in this range</strong><span>Calculated performance highlights require at least one qualifying sales order.</span></div>
              : syntheticOverview?.highlights ? <div className="highlights-grid">
              {([
                ['Highest-revenue month', syntheticOverview.highlights.highest_revenue_month],
                ['Highest-profit month', syntheticOverview.highlights.highest_profit_month],
                ['Lowest-revenue month', syntheticOverview.highlights.lowest_revenue_month],
                ['Highest-sales day', syntheticOverview.highlights.highest_sales_day],
                ['Highest-order day', syntheticOverview.highlights.highest_order_day],
                ['Best-performing weekday', syntheticOverview.highlights.best_weekday],
                ['Top category', syntheticOverview.highlights.best_category],
                ['Strongest quarter', syntheticOverview.highlights.strongest_quarter],
              ] as const).map(([label, point]) => <article className="highlight-item" key={label}>
                <span>{label}</span>
                <strong>{point?.weekday_name ?? point?.category ?? (point?.month ? monthLabel(point.month) : undefined) ?? point?.date ?? (label === 'Strongest quarter' && point?.period ? quarterLabel(point.period) : point?.period) ?? 'No records'}</strong>
                <small>{point?.gross_sales_usd !== undefined ? `${money(Number(point.gross_sales_usd))} gross sales` : point?.gross_profit_usd !== undefined ? `${money(Number(point.gross_profit_usd))} gross profit` : point?.order_count !== undefined ? `${point.order_count.toLocaleString()} orders` : 'No qualifying records in this range'}</small>
                {label === 'Highest-sales day' && point?.average_daily_revenue_usd !== undefined && <small>{money(Number(point.average_daily_revenue_usd))} average daily sales baseline</small>}
              </article>)}
            </div> : <div className="empty-state"><strong>Highlights unavailable</strong><span>Highlights appear when filtered sales records are available.</span></div>}
          </section>

          <section className="surface performance-drivers" aria-labelledby="performance-drivers-title">
            <div className="panel-header"><div><div className="panel-kicker">PERFORMANCE DRIVERS</div><h2 id="performance-drivers-title">What drove this performance?</h2><p>Leading revenue categories and their strongest month in the selected date range.</p></div></div>
            {dataLoading
              ? <div className="driver-grid skeleton-drivers" role="status" aria-label="Loading performance drivers">{Array.from({ length: 3 }, (_, index) => <article className="driver-card" key={index}><span className="skeleton-block"/><span className="skeleton-block"/><span className="skeleton-block"/></article>)}</div>
              : !syntheticOverview
                ? <div className="empty-state"><strong>Performance drivers unavailable</strong><span>{dataError ?? 'The overview response did not include category driver data.'}</span></div>
                : syntheticOverview.category_drivers.length
                  ? <div className="driver-grid">{syntheticOverview.category_drivers.map((driver, index) => <article className="driver-card" key={driver.category}>
                    <div className="driver-card-heading"><div><span>Revenue driver {index + 1}</span><h3>{driver.category}</h3></div><strong>{Number(driver.contribution_pct).toFixed(1)}%</strong></div>
                    <p className="driver-contribution">{money(Number(driver.gross_sales_usd))} of {money(Number(syntheticOverview.gross_sales_usd))} gross sales</p>
                    <div className="driver-best-month"><span>Best-performing month</span><strong>{monthLabel(driver.best_month)}</strong><small>{money(Number(driver.best_month_gross_sales_usd))} gross sales</small></div>
                  </article>)}</div>
                  : <div className="empty-state"><strong>No category drivers in this range</strong><span>Choose a date range with qualifying sales to see what drove performance.</span></div>}
          </section>

          <section className="analysis-grid">
            <article className="surface analysis-card category-card">
              <div className="panel-header compact"><div><div className="panel-kicker">SALES MIX</div><h2>Revenue by category</h2></div><span className="data-tag">LIVE</span></div>
              <div className="category-content" aria-busy={dataLoading}>{dataLoading
                ? <div className="category-skeleton" role="status" aria-label="Loading category mix"><span/><i/><i/><i/></div>
                : <><div className="donut-wrap">{categories.length ? <Suspense fallback={<div className="chart-loading">Loading validated categories...</div>}><CategoryDonut data={categories}/></Suspense> : <div className="chart-loading">No category rows.</div>}<div className="donut-total"><strong>{period.metrics[0]?.value ?? '-'}</strong><span>Gross sales</span></div></div>
                  <div className="category-legend">{categories.map((category) => <div key={category.name}><span><i style={{ background: category.color }}/>{category.name}</span><strong>{category.share}%</strong></div>)}</div></>}</div>
              <div className="card-footnote">Shares are calculated from validated non-cancelled order lines.</div>
            </article>

            <article className="surface analysis-card risk-card">
              <div className="panel-header compact"><div><div className="panel-kicker">CUSTOMER INTELLIGENCE</div><h2>Churn risk distribution</h2></div><button className="quiet-link small-link" onClick={() => goTo('Customer Intelligence')}>Explore <Icon name="arrow" size={12}/></button></div>
              {riskSegments.length ? <div className="risk-summary">{riskSegments.map((segment) => <div key={segment.segment}><span>{segment.segment}</span><strong>{segment.customers.toLocaleString()}</strong><small>{segment.share}% of customers</small></div>)}</div> : <div className="empty-state"><strong>Customer activity unavailable</strong><span>Connect the API to calculate the configured inactivity rule from purchase recency.</span></div>}
              <div className="card-footnote">{syntheticOverview?.churn_rule ? 'Inactive customer screening uses a 90-day no-purchase rule when the API is connected.' : ''}</div>
            </article>

            <article className="surface analysis-card inventory-card">
              <div className="panel-header compact"><div><div className="panel-kicker">INVENTORY HEALTH</div><h2>Stock position</h2></div><button className="quiet-link small-link" onClick={() => goTo('Inventory & Supply Chain')}>Explore <Icon name="arrow" size={12}/></button></div>
              <div className="inventory-summary"><div className="inventory-value"><strong>{syntheticOverview?.latest_inventory_snapshot ? money(Number(syntheticOverview.latest_inventory_value_usd)) : 'No snapshot'}</strong><span>latest inventory value</span></div><div className="inventory-legend"><div><span><i style={{ background: '#5e6259' }}/>Snapshot date</span><strong>{syntheticOverview?.latest_inventory_snapshot ?? '-'}</strong></div><div><span><i style={{ background: '#b87355' }}/>Health classification</span><strong>Not modeled</strong></div></div></div>
              <div className="card-footnote">Point-in-time inventory value is live; health classification is not yet modeled.</div>
            </article>
          </section>

          <section className="surface products-panel">
              <div className="panel-header"><div><div className="panel-kicker">SALES PERFORMANCE</div><h2>Top-performing products</h2><p>Ranking is calculated from non-cancelled order lines.</p></div><button className="quiet-link" onClick={() => goTo('Sales & Revenue')}>View sales detail <Icon name="arrow" size={13}/></button></div>
            <div className="product-table-wrap"><table className="product-table"><thead><tr><th scope="col">PRODUCT</th><th scope="col">CATEGORY</th><th scope="col">REVENUE</th><th scope="col">GROWTH</th></tr></thead><tbody>{products.map((product, index) => <tr key={product.sku}><td><span className={`product-rank rank-${index}`}>{product.sku}</span><span className="product-name">{product.name}</span></td><td><span className="product-category">{product.category}</span></td><td className="product-revenue">{money(product.revenue[periodId])}</td><td><span className="product-growth" title="Product-level growth is not calculated by the current API.">Not calculated</span></td></tr>)}</tbody></table></div>
          </section>

          <section className="surface action-table-panel">
            <div className="panel-header action-table-heading"><div><div className="panel-kicker">MANAGEMENT BY EXCEPTION</div><h2>Priority actions</h2><p>No validated recommendations are available yet.</p></div><div className="table-controls"><label className="filter-select-label">Priority <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option>All priorities</option><option>High</option><option>Medium</option><option>Low</option></select></label><button className="sort-button" onClick={() => setImpactOrder(impactOrder === 'high' ? 'low' : 'high')} aria-label={`Sort estimated impact ${impactOrder === 'high' ? 'ascending' : 'descending'}`}>Impact {impactOrder === 'high' ? '-' : '+'}</button></div></div>
            <div className="action-table-wrap"><table className="action-table"><thead><tr><th scope="col">PRIORITY</th><th scope="col">RECOMMENDED ACTION</th><th scope="col">RELATED ENTITY</th><th scope="col">EST. IMPACT</th><th scope="col">OWNER</th><th scope="col">DUE</th><th scope="col">STATUS</th><th scope="col"><span className="visually-hidden">Open details</span></th></tr></thead><tbody>{filteredActions.map((action) => <tr key={action.id} className={reviewedActions.includes(action.id) ? 'row-reviewed' : ''}><td><span className={`priority-pill ${action.priority.toLowerCase()}`}><i/>{action.priority}</span></td><td><strong className="action-title">{action.title}</strong></td><td className="entity-cell">{action.entity}</td><td className="impact-cell">{money(action.impact)}<small>estimated</small></td><td className="owner-cell">{action.owner}</td><td className="due-cell">{action.due}</td><td><span className={`status-pill ${reviewedActions.includes(action.id) ? 'reviewed' : action.status === 'Draft' ? 'draft' : 'needs-review'}`}>{reviewedActions.includes(action.id) ? 'Reviewed' : action.status}</span></td><td><button className="row-open" onClick={() => setSelectedAction(action)} aria-label={`Open details for ${action.title}`}><Icon name="arrow" size={14}/></button></td></tr>)}</tbody></table>{filteredActions.length === 0 && <div className="table-empty">No validated actions are available yet.</div>}</div>
            <div className="action-table-footer"><span><Icon name="info" size={13}/> Estimates contain assumptions. Review supporting evidence before acting.</span><button onClick={() => goTo('Decision Center')}>View decision workflow <Icon name="arrowRight" size={13}/></button></div>
          </section>

          <footer className="page-footer"><span>BizNexa <i>-</i> Turning business data into measurable decisions.</span><span>Validated dataset when connected <b>-</b> No unverified business results</span></footer>
        </>}
      </div>
    </main>

    {notificationOpen && <div className="notification-popover"><div className="popover-heading"><div><span className="panel-kicker">NOTIFICATIONS</span><strong>Insight signals</strong></div><button onClick={() => setNotificationOpen(false)} aria-label="Close notifications"><Icon name="close" size={16}/></button></div>{insights.map((insight) => <button className="notification-item" key={insight.id} onClick={() => { setNotificationOpen(false); setSelectedInsight(insight) }}><span className="notification-copper-dot"/><span><strong>{insight.title}</strong><small>Validated insight endpoint pending.</small></span></button>)}<div className="notification-note">No notification signals are generated until validated models are connected.</div></div>}

    {(selectedAction || selectedInsight) && <div className="drawer-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDrawer() }}><aside className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="drawer-header"><div><span className="panel-kicker">{selectedAction ? 'RECOMMENDATION DETAIL' : selectedInsight?.kind}</span><span className="drawer-demo-tag">UNVALIDATED</span></div><button className="drawer-close" onClick={closeDrawer} aria-label="Close details"><Icon name="close"/></button></div>
      <h2 id="drawer-title">{selectedAction?.title ?? selectedInsight?.title}</h2>
      <p className="drawer-intro">{selectedAction ? 'Review the evidence and assumptions before deciding whether this draft action is appropriate.' : 'This sample signal demonstrates the evidence and uncertainty a governed decision insight should show.'}</p>
      <div className="drawer-impact"><span>Estimated financial impact</span><strong>{selectedAction ? money(selectedAction.impact) : selectedInsight?.impact}</strong><small>Estimate only - not realized or guaranteed</small></div>
      <div className="drawer-section"><h3>Evidence</h3><p>{selectedAction?.evidence ?? selectedInsight?.evidence}</p></div>
      <div className="drawer-section"><h3>Assumptions and limitations</h3><p>{selectedAction?.assumption ?? selectedInsight?.assumption}</p></div>
      <div className="drawer-section approval-section"><h3>Approval and ownership</h3><dl><div><dt>Status</dt><dd>{selectedAction ? (reviewedActions.includes(selectedAction.id) ? 'Reviewed in this preview' : selectedAction.status) : 'Exploratory signal'}</dd></div><div><dt>Suggested owner</dt><dd>{selectedAction?.owner ?? 'Business owner to be assigned'}</dd></div><div><dt>Action date</dt><dd>{selectedAction?.due ?? 'Not set'}</dd></div></dl></div>
      <div className="drawer-history"><span className="history-dot"/><span><strong>Draft created</strong><small>Illustrative sample - no external action taken</small></span></div>
      <div className="drawer-actions"><button className="drawer-secondary" onClick={closeDrawer}>Close</button>{selectedAction && <button className="drawer-primary" onClick={() => { setReviewedActions((current) => current.includes(selectedAction.id) ? current : [...current, selectedAction.id]); closeDrawer() }}>Mark reviewed in preview</button>}</div>
    </aside></div>}
  </div>
}

const moduleEndpoints: Record<string, string> = {
  'Customer Intelligence': '/api/analytics/synthetic/customers',
  'Sales & Revenue': '/api/analytics/synthetic/sales',
  'Financial Performance': '/api/analytics/synthetic/finance',
  'Inventory & Supply Chain': '/api/analytics/synthetic/inventory',
  'Supplier Intelligence': '/api/analytics/synthetic/suppliers',
  'Decision Center': '/api/analytics/synthetic/decisions',
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'number' && Number.isFinite(value) && !Number.isInteger(value)) {
    return value.toLocaleString('en-US', { useGrouping: false, maximumFractionDigits: 4 })
  }
  if (typeof value === 'string' && /^-?\d+\.\d+$/.test(value)) {
    const decimal = Number(value)
    if (Number.isFinite(decimal)) return decimal.toLocaleString('en-US', { useGrouping: false, maximumFractionDigits: 4 })
  }
  return String(value)
}

const domainTabs: Record<string, string[]> = {
  'Sales & Revenue': ['Overview', 'Sales Trends', 'Product Performance', 'Seasonality', 'Transactions'],
  'Financial Performance': ['Overview', 'Profitability', 'Budget vs Actual', 'Variance Analysis'],
  'Inventory & Supply Chain': ['Overview', 'Stock Health', 'Warehouse Analysis', 'Reorder Analysis', 'Supplier Performance'],
}

function domainTableView(
  section: string,
  tab: string,
  payload: Record<string, unknown> | null,
): { title: string; description: string; rows: Record<string, unknown>[]; fields?: string[] } {
  if (!payload) return { title: tab, description: '', rows: [] }

  if (section === 'Sales & Revenue') {
    if (tab === 'Transactions') {
      return {
        title: tab,
        description: 'Transaction-level records are not currently exposed by the sales analytics API.',
        rows: [],
      }
    }
    const key = tab === 'Product Performance' ? 'top_products'
      : tab === 'Seasonality' ? 'monthly'
        : 'trend'
    const descriptions: Record<string, string> = {
      Overview: 'Reporting-period sales and order aggregates.',
      'Sales Trends': 'Sales and order aggregates at the selected reporting granularity.',
      'Product Performance': 'Top products ranked by validated sales revenue.',
      Seasonality: 'Monthly sales aggregates for the selected date range.',
    }
    return {
      title: tab,
      description: descriptions[tab] ?? '',
      rows: Array.isArray(payload[key]) ? payload[key] as Record<string, unknown>[] : [],
    }
  }

  if (section === 'Financial Performance') {
    const rows = Array.isArray(payload.monthly) ? payload.monthly as Record<string, unknown>[] : []
    const fields: Record<string, string[]> = {
      Overview: ['month', 'category', 'actual_revenue_usd', 'actual_gross_profit_usd', 'revenue_budget_usd', 'variance_usd'],
      Profitability: ['month', 'category', 'actual_revenue_usd', 'actual_gross_profit_usd', 'actual_margin_pct'],
      'Budget vs Actual': ['month', 'category', 'actual_revenue_usd', 'revenue_budget_usd', 'actual_gross_profit_usd', 'gross_margin_target_pct'],
      'Variance Analysis': ['month', 'category', 'variance_usd', 'variance_pct', 'operating_expense_budget_usd'],
    }
    return {
      title: tab,
      description: 'Monthly actuals are compared with the available budget rows for the selected date range.',
      rows,
      fields: fields[tab] ?? fields.Overview,
    }
  }

  if (section === 'Inventory & Supply Chain') {
    if (tab === 'Supplier Performance') {
      return {
        title: tab,
        description: 'Purchase-order delivery and quality measures from the supplier analytics endpoint.',
        rows: Array.isArray(payload.suppliers) ? payload.suppliers as Record<string, unknown>[] : [],
      }
    }
    const items = Array.isArray(payload.items) ? payload.items as Record<string, unknown>[] : []
    if (tab === 'Warehouse Analysis') {
      const byWarehouse = new Map<string, Record<string, unknown>>()
      items.forEach((item) => {
        const warehouse = String(item.warehouse_name ?? item.warehouse_id ?? 'Unknown')
        const group = byWarehouse.get(warehouse) ?? {
          warehouse_name: warehouse,
          product_records: 0,
          low_stock_records: 0,
          inventory_value_usd: 0,
          available_units: 0,
        }
        group.product_records = Number(group.product_records) + 1
        group.low_stock_records = Number(group.low_stock_records) + (item.low_stock ? 1 : 0)
        group.inventory_value_usd = Number(group.inventory_value_usd) + Number(item.inventory_value_usd ?? 0)
        group.available_units = Number(group.available_units) + Number(item.available_qty ?? 0)
        byWarehouse.set(warehouse, group)
      })
      return {
        title: tab,
        description: 'Warehouse totals are grouped from the current inventory snapshot.',
        rows: [...byWarehouse.values()].sort((a, b) => Number(b.inventory_value_usd) - Number(a.inventory_value_usd)),
      }
    }
    const rows = tab === 'Stock Health' ? items.filter((item) => item.low_stock)
      : tab === 'Reorder Analysis' ? items.filter((item) => item.reorder_recommended)
        : items
    return {
      title: tab,
      description: tab === 'Reorder Analysis'
        ? 'Items flagged by the configured low-stock rule, with reorder quantities from product minimums.'
        : 'Current inventory records from the latest available snapshot.',
      rows,
    }
  }

  return { title: tab, description: '', rows: [] }
}

function AnalyticsModule({
  section,
  initialTab,
  onBack,
  onNavigate,
  onTabChange,
  start,
  end,
  granularity,
  overview,
  apiState,
  savedViews,
  savedViewsError,
  onOpenSavedView,
  onDeleteSavedView,
}: {
  section: string
  initialTab: string | null
  onBack: () => void
  onNavigate: (section: string) => void
  onTabChange: (tab: string | null) => void
  start: string
  end: string
  granularity: ReportingGranularity
  overview: SyntheticOverview | null
  apiState: ApiState
  savedViews: SavedView[]
  savedViewsError: string | null
  onOpenSavedView: (savedView: SavedView) => void
  onDeleteSavedView: (id: string) => void
}) {
  const endpoint = moduleEndpoints[section]
  const tabs = domainTabs[section] ?? []
  const [activeTab, setActiveTab] = useState(initialTab && tabs.includes(initialTab) ? initialTab : 'Overview')
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<{
    status: string
    database: {
      status: string
      analytics_schema?: string
      analytics_schema_initialized?: boolean
      missing_tables?: string[]
      missing_columns?: string[]
      detail?: string
      query?: string
    }
  } | null>(null)
  const activeEndpoint = section === 'Inventory & Supply Chain' && activeTab === 'Supplier Performance'
    ? moduleEndpoints['Supplier Intelligence']
    : endpoint

  useEffect(() => {
    setActiveTab(initialTab && tabs.includes(initialTab) ? initialTab : 'Overview')
  }, [section, initialTab])

  useEffect(() => {
    onTabChange(tabs.length ? activeTab : null)
  }, [activeTab, onTabChange, tabs.length])

  useEffect(() => {
    let mounted = true
    setPayload(null)
    setError(null)
    setHealth(null)
    if (section === 'Data Management') {
      apiGet<NonNullable<typeof health>>('/health')
        .then((response) => { if (mounted) setHealth(response) })
        .catch((reason: unknown) => {
          if (mounted) setError(reason instanceof ApiRequestError ? reason.message : 'Database health could not be loaded.')
        })
      return () => { mounted = false }
    }
    if (!activeEndpoint) return () => { mounted = false }
    const params = new URLSearchParams()
    if (section === 'Customer Intelligence') {
      if (end) params.set('as_of', end)
    } else if (section === 'Inventory & Supply Chain' && activeTab !== 'Supplier Performance') {
      if (end) params.set('as_of', end)
    } else {
      if (start) params.set('start', start)
      if (end) params.set('end', end)
      if (section === 'Sales & Revenue') params.set('granularity', granularity)
    }
    const query = params.toString()
    apiGet<Record<string, unknown>>(`${activeEndpoint}${query ? `?${query}` : ''}`)
      .then((body) => mounted && setPayload(body))
      .catch((reason: unknown) => mounted && setError(reason instanceof ApiRequestError ? reason.message : 'Request failed'))
    return () => { mounted = false }
  }, [activeEndpoint, section, start, end, granularity])

  const staticCopy: Record<string, string> = {
    'Predictive Analytics': 'Predictive models are intentionally not claimed until a holdout evaluation is implemented. The customer endpoint provides a configurable inactivity rule for governed churn-risk analysis.',
    'Reports & BI': 'Validated API responses are the source for governed reports. Connect Power BI to the same metric definitions documented in the KPI dictionary.',
    'Data Management': 'Inspect the live API, database connection, imported schema validation, and source dataset period. Credentials remain server-side and are never displayed here.',
    'Settings': 'Workspace settings use the backend environment configuration. Secrets remain server-side and are never sent to the browser.',
  }

  const rows = payload ? Object.entries(payload).filter(([key, value]) => !['trend', 'monthly', 'categories', 'top_products', 'items', 'suppliers', 'segments', 'actions'].includes(key) && typeof value !== 'object') : []
  const view = domainTableView(section, activeTab, payload)
  const fields = view.fields ?? (view.rows[0] ? Object.keys(view.rows[0]).slice(0, 7) : [])
  const isBusinessDomain = tabs.length > 0
  const isDecisionCenter = section === 'Decision Center'
  const decisionActions = payload && Array.isArray(payload.actions)
    ? payload.actions as Record<string, unknown>[]
    : []
  const decisionMethod = typeof payload?.method === 'string' ? payload.method : ''
  const decisionPeriod = payload?.reporting_period && typeof payload.reporting_period === 'object'
    ? payload.reporting_period as { start?: unknown; end?: unknown }
    : null
  const highPriorityActions = decisionActions.filter((action) => action.priority === 'High').length

  if (section === 'Saved Views') {
    return <section className="module-placeholder saved-views-workspace">
      <header className="saved-views-heading">
        <div><div className="panel-kicker">WORKSPACE</div><h1>Saved Views</h1><p>Bookmarks for dashboards, reports, and their reporting-period filters.</p></div>
        <span className="saved-views-count">{savedViews.length} {savedViews.length === 1 ? 'saved view' : 'saved views'}</span>
      </header>
      {savedViewsError && <div className="module-error" role="alert"><strong>Storage unavailable</strong><span>{savedViewsError}</span></div>}
      {savedViews.length ? <div className="saved-view-list">{savedViews.map((savedView) => <article className="saved-view-card" key={savedView.id}>
        <span className="saved-view-icon"><Icon name="bookmark" size={17}/></span>
        <div className="saved-view-details"><strong>{savedView.name}</strong>
          <span>{savedView.start || savedView.end ? `${savedView.start || 'Start'} — ${savedView.end || 'End'}` : 'Available reporting period'}</span>
          <small>{savedView.granularity} granularity · {savedView.comparison.replaceAll('_', ' ')}</small>
        </div>
        <div className="saved-view-actions">
          <button type="button" className="saved-view-open" onClick={() => onOpenSavedView(savedView)}>Open view</button>
          <button type="button" className="saved-view-delete" onClick={() => onDeleteSavedView(savedView.id)} aria-label={`Remove ${savedView.name}`}>Remove</button>
        </div>
      </article>)}</div> : <div className="saved-views-empty">
        <span className="saved-view-icon"><Icon name="bookmark" size={18}/></span>
        <strong>No saved views yet</strong>
        <span>Open a dashboard or report, set its reporting period, then choose <b>Save view</b> in the top bar.</span>
      </div>}
    </section>
  }

  return <section className={`module-placeholder ${isBusinessDomain ? 'domain-workspace' : ''} ${isDecisionCenter ? 'decision-workspace' : ''}`}>
    {isBusinessDomain && <div className="domain-tabs" role="tablist" aria-label={`${section} sections`}>
      {tabs.map((tab, index) => <button key={tab} id={`domain-tab-${index}`} type="button" role="tab" aria-selected={activeTab === tab} aria-controls="domain-analysis-panel" className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)}>{tab}</button>)}
    </div>}
    {isDecisionCenter ? <header className="decision-header">
      <div className="decision-heading">
        <span className="module-mark"><Icon name="decision" size={22}/></span>
        <div><div className="panel-kicker">DECISION INTELLIGENCE</div><h1>{section}</h1>
          <p>Evidence-based prompts from current inventory and customer activity. Review before taking action.</p></div>
      </div>
      <div className="decision-context">
        {Boolean(decisionPeriod?.start && decisionPeriod.end) && <span className="decision-period">{displayValue(decisionPeriod?.start)} — {displayValue(decisionPeriod?.end)}</span>}
        {payload?.synthetic === true && <span className="decision-source">Validated synthetic data</span>}
      </div>
    </header> : <>
      <span className="module-mark"><Icon name={section === 'Inventory & Supply Chain' ? 'inventory' : section === 'Customer Intelligence' ? 'customers' : 'reports'} size={22}/></span>
      <div className="panel-kicker">{activeEndpoint ? 'VALIDATED DATA MODULE' : 'WORKSPACE MODULE'}</div>
      <h1>{section}</h1>
      <p>{error ? `The module could not load live data: ${error}` : isBusinessDomain ? view.description : staticCopy[section] ?? (payload ? 'Live metrics from the validated synthetic dataset.' : activeEndpoint ? 'Loading validated metrics from the BizNexa API...' : 'This workspace module is ready for validated data and governed reporting.')}</p>
    </>}
    {error && <div className="module-error"><strong>Live data unavailable</strong><span>Start the API and initialize the development schema before retrying this module.</span></div>}
    {section === 'Data Management' && <>
      <div className="module-metrics">
        <div><span>API state</span><strong>{apiState}</strong></div>
        <div><span>Dataset</span><strong>{overview?.dataset ?? 'Unavailable'}</strong></div>
        <div><span>Source type</span><strong>{overview ? (overview.synthetic ? 'Synthetic' : 'Business data') : 'Unavailable'}</strong></div>
        <div><span>Available data period</span><strong>{overview ? `${overview.available_period.start} — ${overview.available_period.end}` : 'Unavailable'}</strong></div>
        <div><span>Selected reporting period</span><strong>{overview ? `${overview.reporting_period.start} — ${overview.reporting_period.end}` : 'Unavailable'}</strong></div>
        <div><span>Database</span><strong>{health?.database.status ?? 'Not validated'}</strong></div>
        <div><span>Analytics schema</span><strong>{health?.database.analytics_schema ?? 'Unavailable'}</strong></div>
        <div><span>Schema validation</span><strong>{health?.database.analytics_schema_initialized === true ? 'Complete' : health?.database.analytics_schema_initialized === false ? 'Incomplete' : 'Unavailable'}</strong></div>
        <div><span>Health query</span><strong>{health?.database.query ?? 'Unavailable'}</strong></div>
      </div>
      {health?.database.detail && <div className="module-error"><strong>Database status</strong><span>{health.database.detail}</span></div>}
      {health?.database.missing_tables?.length ? <div className="module-error"><strong>Missing tables</strong><span>{health.database.missing_tables.join(', ')}</span></div> : null}
      {health?.database.missing_columns?.length ? <div className="module-error"><strong>Missing columns</strong><span>{health.database.missing_columns.join(', ')}</span></div> : null}
      {overview?.sales_policy && <div className="customer-reconciliation-note">Revenue policy: {overview.sales_policy} Return policy: {overview.return_policy}</div>}
    </>}
    {isDecisionCenter && !payload && !error && <div className="decision-loading" role="status">Loading recommendations…</div>}
    {payload && <>
      {isDecisionCenter ? <>
        <BusinessPulse start={start} end={end} onNavigate={onNavigate}/>
        <WhatIfSimulator start={start} end={end}/>
        <section className="decision-summary" aria-label="Recommendation summary">
          <article><span>Open recommendations</span><strong>{decisionActions.length.toLocaleString()}</strong><small>Based on the selected reporting context</small></article>
          <article><span>High priority</span><strong>{highPriorityActions.toLocaleString()}</strong><small>Requires business review</small></article>
          {decisionMethod && <p className="decision-method"><span>Method</span>{decisionMethod}</p>}
        </section>
        <section className="decision-recommendations" aria-labelledby="decision-recommendations-title">
          <div className="decision-section-heading"><div><div className="panel-kicker">REVIEW QUEUE</div><h2 id="decision-recommendations-title">Recommendations</h2></div><span>{decisionActions.length.toLocaleString()} items</span></div>
          {decisionActions.length ? <div className="decision-action-list">
            {decisionActions.map((action, index) => <article className="decision-action-card" key={String(action.id ?? index)}>
              <div className="decision-action-top">
                <span className={`decision-priority decision-priority-${String(action.priority ?? 'low').toLowerCase()}`}>{displayValue(action.priority)}</span>
                <span className="decision-supporting-metric"><strong>{displayValue(action.supporting_metric)}</strong><small>Supporting metric</small></span>
              </div>
              <h3>{displayValue(action.title)}</h3>
              <p>{displayValue(action.reason)}</p>
              <div className="decision-suggested-action"><span>Suggested next step</span><strong>{displayValue(action.suggested_action)}</strong></div>
            </article>)}
          </div> : <div className="decision-empty"><strong>No recommendations for this period</strong><span>There are no current threshold-based actions to review.</span></div>}
        </section>
      </> : <div className="module-metrics">{rows.slice(0, 6).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{displayValue(value)}</strong></div>)}</div>}
      {isBusinessDomain && <section className="domain-analysis-panel" id="domain-analysis-panel" role="tabpanel" aria-labelledby={`domain-tab-${tabs.indexOf(activeTab)}`}>
        <div className="domain-analysis-heading"><h2>{view.title}</h2><span>{view.rows.length.toLocaleString()} records</span></div>
        {view.rows.length > 0 ? <div className="module-table-wrap"><table className="module-table"><thead><tr>{fields.map((key) => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{view.rows.slice(0, 100).map((row, index) => <tr key={index}>{fields.map((key) => <td key={key}>{displayValue(row[key])}</td>)}</tr>)}</tbody></table></div>
          : <p className="domain-empty">{section === 'Sales & Revenue' && activeTab === 'Transactions'
            ? 'Order-level transaction data is not exposed by the current analytics API. The available sales views use validated aggregates.'
            : 'No records are available for this view in the selected reporting period.'}</p>}
      </section>}
      {!isBusinessDomain && !isDecisionCenter && (() => {
        const listKey = ['trend', 'monthly', 'categories', 'top_products', 'items', 'suppliers', 'segments', 'actions'].find((key) => Array.isArray(payload[key]))
        const list = listKey ? payload[listKey] as Record<string, unknown>[] : []
        return list.length > 0 ? <div className="module-table-wrap"><table className="module-table"><thead><tr>{Object.keys(list[0]).slice(0, 5).map((key) => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{list.slice(0, 12).map((row, index) => <tr key={index}>{Object.keys(list[0]).slice(0, 5).map((key) => <td key={key}>{displayValue(row[key])}</td>)}</tr>)}</tbody></table></div> : null
      })()}
    </>}
    {isDecisionCenter && <DecisionImpactTracker/>}
    {!isBusinessDomain && !isDecisionCenter && <>
      <div className="module-checklist"><span><i/> Business definition</span><span><i/> Source query</span><span><i/> Decision context</span></div>
      <button className="module-back" onClick={onBack}>Return to executive overview <Icon name="arrowRight" size={15}/></button>
    </>}
  </section>
}

export default App
