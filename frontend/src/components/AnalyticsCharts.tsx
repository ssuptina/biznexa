import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'

type TrendPoint = { period: string; revenue: number; profit: number; margin: number }
type CategoryPoint = { name: string; share: number; color: string }
type CustomerChartPoint = { name: string; value: number; color?: string }
type CustomerTrendPoint = {
  month: string
  active_customers: number
  new_customers: number
  returning_customers: number
}
const customerColors = ['#b87355', '#5a5b54', '#aaa18f', '#8e9b86', '#d2bda6']

function RevenueTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color?: string }[]; label?: string }) {
  if (!active || !payload?.length) return null
  return <div className="chart-tooltip"><strong>{label}</strong>{payload.map((entry) => <div key={entry.name}><i style={{ background: entry.color }}/>{entry.name}<b>{entry.name === 'Gross margin' ? `${entry.value.toFixed(1)}%` : `$${entry.value.toFixed(2)}M`}</b></div>)}</div>
}

export function RevenueChart({ data }: { data: TrendPoint[] }) {
  const tickInterval = Math.max(0, Math.ceil(data.length / 8) - 1)
  const formatPeriodTick = (period: string) => {
    const month = /^(\d{4})-(\d{2})$/.exec(period)
    if (!month) return period
    return new Date(Date.UTC(Number(month[1]), Number(month[2]) - 1, 1))
      .toLocaleDateString('en-US', { month: 'short', year: '2-digit', timeZone: 'UTC' })
  }

  return <>
    <div className="chart-legend" aria-label="Chart series">
      <span><i className="legend-swatch revenue"/>Revenue</span>
      <span><i className="legend-swatch profit"/>Gross profit</span>
      <span><i className="legend-swatch margin"/>Gross margin</span>
    </div>
    <div className="revenue-chart" role="img" aria-label="Revenue, gross profit, and gross margin chart from the validated dataset">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 12, right: 8, bottom: 0, left: 2 }}>
          <CartesianGrid stroke="#eae5dc" strokeDasharray="2 4" vertical={false}/>
          <XAxis dataKey="period" tickLine={false} axisLine={false} tick={{ fill: '#8b8983', fontSize: 9 }} interval={tickInterval} tickFormatter={formatPeriodTick} dy={9}/>
          <YAxis yAxisId="money" tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} tickFormatter={(value: number) => `$${value.toFixed(1)}M`} width={39} domain={[0, 'dataMax + 0.15']}/>
          <YAxis yAxisId="percent" orientation="right" tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} tickFormatter={(value: number) => `${value}%`} width={34} domain={[0, 50]}/>
          <Tooltip content={<RevenueTooltip/>} cursor={{ fill: '#f6f2ed' }}/>
          <Bar yAxisId="money" dataKey="revenue" name="Revenue" fill="#b87355" radius={[3, 3, 0, 0]} maxBarSize={25} isAnimationActive={data.length <= 120}/>
          <Bar yAxisId="money" dataKey="profit" name="Gross profit" fill="#5a5b54" radius={[3, 3, 0, 0]} maxBarSize={25} isAnimationActive={data.length <= 120}/>
          <Line yAxisId="percent" type="monotone" dataKey="margin" name="Gross margin" stroke="#aaa18f" strokeWidth={2} dot={false} activeDot={{ r: 5 }} isAnimationActive={data.length <= 120}/>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  </>
}

export function CustomerSegmentDonut({ data }: { data: CustomerChartPoint[] }) {
  return <ResponsiveContainer width="100%" height="100%">
    <PieChart>
      <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="88%" paddingAngle={2} stroke="none" isAnimationActive={false}>
        {data.map((item, index) => <Cell key={item.name} fill={item.color ?? customerColors[index % customerColors.length]}/>)}
      </Pie>
      <Tooltip formatter={(value) => [Number(value).toLocaleString(), 'Customers']} contentStyle={{ borderRadius: 7, borderColor: '#e4ded5', fontSize: 10 }}/>
    </PieChart>
  </ResponsiveContainer>
}

export function CustomerBarChart({
  data,
  valueLabel,
  horizontal = false,
}: {
  data: CustomerChartPoint[]
  valueLabel: string
  horizontal?: boolean
}) {
  if (horizontal) return <ResponsiveContainer width="100%" height="100%">
    <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 3 }}>
      <CartesianGrid stroke="#eee9e2" strokeDasharray="2 4" horizontal={false}/>
      <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }}/>
      <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} tick={{ fill: '#858078', fontSize: 8 }} width={150}/>
      <Tooltip formatter={(value) => [Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }), valueLabel]} contentStyle={{ borderRadius: 7, borderColor: '#e4ded5', fontSize: 10 }}/>
      <Bar dataKey="value" name={valueLabel} fill="#b87355" radius={[0, 3, 3, 0]} maxBarSize={20} isAnimationActive={false}/>
    </BarChart>
  </ResponsiveContainer>

  return <ResponsiveContainer width="100%" height="100%">
    <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
      <CartesianGrid stroke="#eee9e2" strokeDasharray="2 4" vertical={false}/>
      <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fill: '#858078', fontSize: 9 }} interval={0} angle={-15} textAnchor="end" height={40}/>
      <YAxis tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} width={43}/>
      <Tooltip formatter={(value) => [Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }), valueLabel]} contentStyle={{ borderRadius: 7, borderColor: '#e4ded5', fontSize: 10 }}/>
      <Bar dataKey="value" name={valueLabel} fill="#b87355" radius={[3, 3, 0, 0]} maxBarSize={38} isAnimationActive={false}/>
    </ComposedChart>
  </ResponsiveContainer>
}

export function CustomerTrendChart({ data }: { data: CustomerTrendPoint[] }) {
  return <ResponsiveContainer width="100%" height="100%">
    <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 2, left: 0 }}>
      <CartesianGrid stroke="#eee9e2" strokeDasharray="2 4" vertical={false}/>
      <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fill: '#858078', fontSize: 9 }} interval={Math.max(0, Math.ceil(data.length / 8) - 1)} tickFormatter={(value: string) => {
        const month = /^(\d{4})-(\d{2})/.exec(value)
        return month ? new Date(Date.UTC(Number(month[1]), Number(month[2]) - 1, 1))
          .toLocaleDateString('en-US', { month: 'short', year: '2-digit', timeZone: 'UTC' }) : value
      }}/>
      <YAxis tickLine={false} axisLine={false} tick={{ fill: '#96938c', fontSize: 9 }} width={35}/>
      <Tooltip formatter={(value, name) => [Number(value).toLocaleString(), name]} contentStyle={{ borderRadius: 7, borderColor: '#e4ded5', fontSize: 10 }}/>
      <Line type="monotone" dataKey="active_customers" name="Active customers" stroke="#5a5b54" strokeWidth={2} dot={false} isAnimationActive={false}/>
      <Line type="monotone" dataKey="new_customers" name="New customers" stroke="#b87355" strokeWidth={2} dot={false} isAnimationActive={false}/>
      <Line type="monotone" dataKey="returning_customers" name="Returning customers" stroke="#aaa18f" strokeWidth={2} dot={false} isAnimationActive={false}/>
    </ComposedChart>
  </ResponsiveContainer>
}

export function CategoryDonut({ data }: { data: CategoryPoint[] }) {
  return <ResponsiveContainer width="100%" height="100%">
    <PieChart>
      <Pie data={data} dataKey="share" nameKey="name" innerRadius="69%" outerRadius="91%" paddingAngle={2} stroke="none">
        {data.map((category) => <Cell key={category.name} fill={category.color}/>) }
      </Pie>
      <Tooltip formatter={(value) => [`${value}%`, 'Validated category share']} contentStyle={{ borderRadius: 7, borderColor: '#e4ded5', fontSize: 11 }}/>
    </PieChart>
  </ResponsiveContainer>
}

type DailySalesPoint = {
  date: string
  gross_sales_usd: string
  gross_profit_usd: string
  order_count: number
}

export function SalesHeatmap({
  data,
  onSelectDate,
}: {
  data: DailySalesPoint[]
  onSelectDate: (date: string) => void
}) {
  if (!data.length) return <div className="chart-loading">No daily sales records exist for this date range.</div>
  const firstDate = new Date(`${data[0].date}T00:00:00Z`)
  const lastDate = new Date(`${data[data.length - 1].date}T00:00:00Z`)
  const firstMonday = new Date(firstDate)
  const firstDay = (firstMonday.getUTCDay() + 6) % 7
  firstMonday.setUTCDate(firstMonday.getUTCDate() - firstDay)
  const weeks = Math.floor((lastDate.getTime() - firstMonday.getTime()) / (7 * 86400000)) + 1
  const maxSales = Math.max(...data.map((point) => Number(point.gross_sales_usd)))
  const byDate = new Map(data.map((point) => [point.date, point]))
  const days = []
  for (let week = 0; week < weeks; week += 1) {
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const current = new Date(firstMonday)
      current.setUTCDate(firstMonday.getUTCDate() + week * 7 + weekday)
      const dateKey = current.toISOString().slice(0, 10)
      const point = byDate.get(dateKey)
      if (point) days.push({ point, week, weekday })
    }
  }
  const monthLabels = data
    .filter((point) => point.date.slice(8) === '01')
    .map((point) => {
      const current = new Date(`${point.date}T00:00:00Z`)
      const week = Math.floor((current.getTime() - firstMonday.getTime()) / (7 * 86400000))
      return { label: current.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' }), week }
    })
  const intensity = (value: number) => {
    if (value <= 0 || maxSales <= 0) return 0
    const share = value / maxSales
    return share >= 0.75 ? 3 : share >= 0.4 ? 2 : 1
  }

  return <div className="sales-heatmap-scroll">
    <div className="sales-heatmap" style={{ gridTemplateColumns: `24px repeat(${weeks}, 11px)` }}>
      <div className="heatmap-month-labels" style={{ gridTemplateColumns: `repeat(${weeks}, 11px)` }} aria-hidden="true">
        {monthLabels.map((month) => <span key={`${month.label}-${month.week}`} style={{ gridColumn: month.week + 1 }}>{month.label}</span>)}
      </div>
      {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => <span className="heatmap-weekday" key={`${day}-${index}`} style={{ gridColumn: 1, gridRow: index + 2 }}>{day}</span>)}
      {days.map(({ point, week, weekday }) => {
        const sales = Number(point.gross_sales_usd)
        const key = `${point.date}-${week}`
        return <button
          key={key}
          type="button"
          className={`heatmap-day heat-level-${intensity(sales)}`}
          style={{ gridColumn: week + 2, gridRow: weekday + 2 }}
          title={`${point.date} · ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(sales)} gross sales · ${point.order_count} orders`}
          aria-label={`${point.date}: ${sales.toFixed(2)} dollars gross sales, ${point.order_count} orders. Select date.`}
          onClick={() => onSelectDate(point.date)}
        />
      })}
    </div>
    <p className="heatmap-help">Hover for daily sales and order count. Select a day to apply it to the dashboard date filter.</p>
  </div>
}
