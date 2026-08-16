import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { formatDataValue, hasDisplayValue } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Kpi } from '@/lib/data'

const toneAccent: Record<NonNullable<Kpi['tone']>, string> = {
  default: 'bg-primary',
  neutral: 'bg-slate-400',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-destructive',
}

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const tone = kpi.tone ?? 'default'
  const positive = kpi.delta?.direction === 'up'
  const value = formatDataValue(kpi.value, 2)

  return (
    <Card className="relative gap-0 overflow-hidden p-5">
      <span className={cn('absolute inset-y-0 left-0 w-1', toneAccent[tone])} aria-hidden />
      <p className="text-sm font-medium text-muted-foreground">{kpi.label}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tracking-tight text-foreground">
          {value}{kpi.unit && hasDisplayValue(kpi.value) ? <span className="ml-1 text-sm">{kpi.unit}</span> : null}
        </span>
        {kpi.delta && hasDisplayValue(kpi.value) ? (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 text-xs font-medium',
              positive ? 'text-success' : 'text-muted-foreground',
            )}
          >
            {positive ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
            {kpi.delta.value}
          </span>
        ) : null}
      </div>
      {kpi.hint ? <p className="mt-1 text-xs text-muted-foreground">{kpi.hint}</p> : null}
    </Card>
  )
}
