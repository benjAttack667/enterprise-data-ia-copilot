import { cn } from '@/lib/utils'
import type { Severity } from '@/lib/data'

const styles: Record<Severity, string> = {
  critical: 'bg-destructive/10 text-destructive ring-destructive/20',
  high: 'bg-warning/15 text-warning-foreground ring-warning/30',
  medium: 'bg-primary/10 text-primary ring-primary/20',
  low: 'bg-muted text-muted-foreground ring-border',
}

const labels: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        styles[severity],
        className,
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          severity === 'critical' && 'bg-destructive',
          severity === 'high' && 'bg-warning',
          severity === 'medium' && 'bg-primary',
          severity === 'low' && 'bg-muted-foreground',
        )}
      />
      {labels[severity]}
    </span>
  )
}
