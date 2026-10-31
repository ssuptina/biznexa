import { useEffect, useState } from 'react'

export type ReportingGranularity = 'day' | 'week' | 'month' | 'quarter' | 'year'
export type PeriodComparison = 'previous_period' | 'same_period_last_year' | 'none'

type ReportingPeriodFilterProps = {
  start: string
  end: string
  availableStart: string
  availableEnd: string
  granularity: ReportingGranularity
  comparison: PeriodComparison
  onApply: (filters: {
    start: string
    end: string
    granularity: ReportingGranularity
    comparison: PeriodComparison
  }) => void
  onReset: () => void
}

type DateRange = { start: string; end: string }

const dateString = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const clampDate = (value: string, minimum: string, maximum: string) => {
  if (minimum && value < minimum) return minimum
  if (maximum && value > maximum) return maximum
  return value
}

const dateRange = (year: number, month: number, availableStart: string, availableEnd: string): DateRange => {
  const first = `${year}-${String(month + 1).padStart(2, '0')}-01`
  const last = dateString(new Date(year, month + 1, 0))
  return {
    start: clampDate(first, availableStart, availableEnd),
    end: clampDate(last, availableStart, availableEnd),
  }
}

export function ReportingPeriodFilter({
  start,
  end,
  availableStart,
  availableEnd,
  granularity,
  comparison,
  onApply,
  onReset,
}: ReportingPeriodFilterProps) {
  const [draft, setDraft] = useState({ start, end, granularity, comparison })

  useEffect(() => {
    setDraft({ start, end, granularity, comparison })
  }, [start, end, granularity, comparison])

  const selectedYear = draft.start ? Number(draft.start.slice(0, 4)) : ''
  const isFullYear = selectedYear !== ''
    && draft.start === `${selectedYear}-01-01`
    && draft.end === `${selectedYear}-12-31`
  const selectedMonth = draft.start && !isFullYear ? Number(draft.start.slice(5, 7)) - 1 : ''
  const selectedDay = draft.start && draft.start === draft.end ? Number(draft.start.slice(8, 10)) : ''
  const firstAvailableYear = availableStart ? Number(availableStart.slice(0, 4)) : 0
  const lastAvailableYear = availableEnd ? Number(availableEnd.slice(0, 4)) : 0
  const years = availableStart && availableEnd
    ? Array.from({ length: Math.max(0, lastAvailableYear - firstAvailableYear + 1) }, (_, index) => firstAvailableYear + index)
    : []
  const months = selectedYear === ''
    ? []
    : Array.from({ length: 12 }, (_, month) => month).filter((month) => {
      const { start: monthStart, end: monthEnd } = dateRange(selectedYear, month, availableStart, availableEnd)
      return monthStart.slice(0, 7) === monthEnd.slice(0, 7)
    })
  const days = selectedYear === '' || selectedMonth === ''
    ? []
    : Array.from({ length: new Date(selectedYear, selectedMonth + 1, 0).getDate() }, (_, index) => index + 1)
      .filter((day) => {
        const value = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        return (!availableStart || value >= availableStart) && (!availableEnd || value <= availableEnd)
      })
  const invalidRange = Boolean(draft.start && draft.end && draft.start > draft.end)

  const updateDates = (range: DateRange) => setDraft((current) => ({ ...current, ...range }))

  return (
    <div className="reporting-filters" aria-label="Reporting period filters">
      <label className="reporting-field reporting-year">
        <span>Year</span>
        <select
          value={selectedYear}
          onChange={(event) => {
            if (!event.target.value) {
              updateDates({ start: '', end: '' })
              return
            }
            const year = Number(event.target.value)
            const first = clampDate(`${year}-01-01`, availableStart, availableEnd)
            const last = clampDate(`${year}-12-31`, availableStart, availableEnd)
            updateDates({ start: first, end: last })
          }}
        >
          <option value="">All years</option>
          {years.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
      </label>
      <label className="reporting-field reporting-month">
        <span>Month</span>
        <select
          value={selectedMonth}
          disabled={selectedYear === ''}
          onChange={(event) => {
            if (!event.target.value) {
              const year = Number(selectedYear)
              updateDates({
                start: clampDate(`${year}-01-01`, availableStart, availableEnd),
                end: clampDate(`${year}-12-31`, availableStart, availableEnd),
              })
              return
            }
            updateDates(dateRange(Number(selectedYear), Number(event.target.value), availableStart, availableEnd))
          }}
        >
          <option value="">{selectedYear === '' ? 'Select year first' : 'All months'}</option>
          {months.map((month) => <option key={month} value={month}>{new Date(2000, month, 1).toLocaleDateString('en-US', { month: 'long' })}</option>)}
        </select>
      </label>
      <label className="reporting-field reporting-day">
        <span>Day</span>
        <select
          value={selectedDay}
          disabled={selectedYear === '' || selectedMonth === ''}
          onChange={(event) => {
            if (!event.target.value) {
              updateDates(dateRange(Number(selectedYear), Number(selectedMonth), availableStart, availableEnd))
              return
            }
            const selectedDate = `${selectedYear}-${String(Number(selectedMonth) + 1).padStart(2, '0')}-${String(Number(event.target.value)).padStart(2, '0')}`
            updateDates({ start: selectedDate, end: selectedDate })
          }}
        >
          <option value="">{selectedYear === '' ? 'Select year first' : selectedMonth === '' ? 'Select month first' : 'All days'}</option>
          {days.map((day) => <option key={day} value={day}>{day}</option>)}
        </select>
      </label>
      <label className="reporting-field reporting-start">
        <span>Start date</span>
        <input
          type="date"
          value={draft.start}
          min={availableStart || undefined}
          max={availableEnd || undefined}
          onChange={(event) => setDraft((current) => ({ ...current, start: event.target.value }))}
          aria-label="Start date"
        />
      </label>
      <label className="reporting-field reporting-end">
        <span>End date</span>
        <input
          type="date"
          value={draft.end}
          min={availableStart || undefined}
          max={availableEnd || undefined}
          onChange={(event) => setDraft((current) => ({ ...current, end: event.target.value }))}
          aria-label="End date"
        />
      </label>
      <label className="reporting-field reporting-granularity">
        <span>Group by</span>
        <select value={draft.granularity} onChange={(event) => setDraft((current) => ({ ...current, granularity: event.target.value as ReportingGranularity }))}>
          <option value="day">Daily</option>
          <option value="week">Weekly</option>
          <option value="month">Monthly</option>
          <option value="quarter">Quarterly</option>
          <option value="year">Yearly</option>
        </select>
      </label>
      <label className="reporting-field reporting-comparison">
        <span>Compare with</span>
        <select value={draft.comparison} onChange={(event) => setDraft((current) => ({ ...current, comparison: event.target.value as PeriodComparison }))}>
          <option value="previous_period">Previous period</option>
          <option value="same_period_last_year">Previous year</option>
          <option value="none">None</option>
        </select>
      </label>
      <div className="reporting-actions">
        <button
          className="reporting-apply"
          type="button"
          disabled={invalidRange}
          onClick={() => onApply(draft)}
        >
          Apply filters
        </button>
        <button className="reporting-reset" type="button" onClick={onReset}>Reset</button>
      </div>
      {invalidRange && <span className="reporting-range-error" role="alert">Start date must be on or before end date.</span>}
      {(!availableStart || !availableEnd) && <span className="reporting-data-note" role="status">Year, month, and day options will load when analytics data is available. You can enter dates manually.</span>}
    </div>
  )
}
