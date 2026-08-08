'use client'

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type {
  CategoryPoint,
  DashboardDatum,
  MissingPoint,
  QualityPoint,
  TrendPoint,
} from '@/lib/data'

const axisProps = {
  stroke: 'var(--muted-foreground)',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
}

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid var(--border)',
  background: 'var(--popover)',
  color: 'var(--popover-foreground)',
  fontSize: 12,
  boxShadow: '0 4px 12px rgba(15,23,42,0.08)',
}

function ChartEmpty() {
  return <div className="flex h-[260px] items-center justify-center text-sm text-muted-foreground">Aucune donnée à afficher.</div>
}

export function QualityByColumnChart({ data }: { data: QualityPoint[] }) {
  if (!data.length) return <ChartEmpty />
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis dataKey="column" {...axisProps} interval={0} angle={-12} textAnchor="end" height={44} />
        <YAxis domain={[0, 100]} {...axisProps} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--muted)' }} />
        <Bar dataKey="score" name="Score qualité" radius={[6, 6, 0, 0]} maxBarSize={44}>
          {data.map((entry) => (
            <Cell
              key={entry.column}
              fill={entry.score >= 85 ? 'var(--chart-2)' : entry.score >= 65 ? 'var(--chart-3)' : 'var(--chart-4)'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function MissingValuesChart({ data }: { data: MissingPoint[] }) {
  if (!data.length) return <ChartEmpty />
  const normalized = data.map((point) => ({ ...point, missing: point.missing ?? point.missing_rate ?? 0 }))
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={normalized} layout="vertical" margin={{ top: 4, right: 16, left: 24, bottom: 0 }}>
        <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis type="number" unit="%" {...axisProps} />
        <YAxis type="category" dataKey="column" width={96} {...axisProps} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--muted)' }} />
        <Bar dataKey="missing" name="Valeurs manquantes (%)" fill="var(--chart-1)" radius={[0, 6, 6, 0]} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function OverviewTrendChart({ data }: { data: TrendPoint[] }) {
  if (!data.length) return <ChartEmpty />
  const normalized = data.map((point, index) => {
    const numericKey = Object.keys(point).find((key) => key !== 'label' && key !== 'date' && key !== 'period' && typeof point[key] === 'number')
    return {
      label: point.label ?? point.date ?? point.period ?? String(index + 1),
      value: point.value ?? (numericKey ? Number(point[numericKey]) : 0),
    }
  })
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={normalized} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: 'var(--border)' }} />
        <Area type="monotone" dataKey="value" name="Valeur" stroke="var(--chart-1)" strokeWidth={2} fill="url(#trendFill)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

const chartColors = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)']

export function CategoryBreakdownChart({ data }: { data: CategoryPoint[] }) {
  if (!data.length) return <ChartEmpty />
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <ResponsiveContainer width="100%" height={220} className="max-w-[220px]">
        <PieChart>
          <Tooltip contentStyle={tooltipStyle} />
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2} strokeWidth={0}>
            {data.map((entry, index) => <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <ul className="grid w-full grid-cols-2 gap-3 sm:grid-cols-1">
        {data.map((entry, index) => (
          <li key={entry.name} className="flex items-center justify-between gap-2 text-sm">
            <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
              <span className="size-2.5 shrink-0 rounded-full" style={{ background: chartColors[index % chartColors.length] }} />
              <span className="truncate">{entry.name}</span>
            </span>
            <span className="font-mono font-medium text-foreground">{entry.value.toLocaleString('fr-FR')}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function DashboardChart({
  data,
  chartType,
  dimension,
  metric,
}: {
  data: DashboardDatum[]
  chartType: string
  dimension: string
  metric: string
}) {
  if (!data.length) return <ChartEmpty />
  const first = data[0]
  const labelKey = 'label' in first ? 'label' : dimension
  const valueKey = 'value' in first ? 'value' : metric

  if (chartType === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={360}>
        <PieChart>
          <Tooltip contentStyle={tooltipStyle} />
          <Pie data={data} dataKey={valueKey} nameKey={labelKey} innerRadius={80} outerRadius={135} paddingAngle={2} strokeWidth={0}>
            {data.map((_, index) => <Cell key={index} fill={chartColors[index % chartColors.length]} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'line' || chartType === 'area') {
    return (
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 24 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
          <XAxis dataKey={labelKey} {...axisProps} angle={-10} textAnchor="end" height={48} />
          <YAxis {...axisProps} />
          <Tooltip contentStyle={tooltipStyle} />
          <Line type="monotone" dataKey={valueKey} name={metric} stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={360}>
      <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 24 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis dataKey={labelKey} {...axisProps} angle={-10} textAnchor="end" height={48} />
        <YAxis {...axisProps} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--muted)' }} />
        <Bar dataKey={valueKey} name={metric} fill="var(--chart-1)" radius={[6, 6, 0, 0]} maxBarSize={56} />
      </BarChart>
    </ResponsiveContainer>
  )
}
