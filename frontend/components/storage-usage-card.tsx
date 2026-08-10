'use client'

import { CircleCheck, HardDrive, TriangleAlert } from 'lucide-react'
import type { StorageUsage } from '@/lib/data'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress'

const ALERT_THRESHOLD = 80

function formatBytes(bytes: number) {
  const normalized = Number.isFinite(bytes) ? Math.max(0, bytes) : 0
  if (normalized === 0) return '0 octet'

  const units = ['octets', 'Kio', 'Mio', 'Gio', 'Tio']
  const exponent = Math.min(Math.floor(Math.log(normalized) / Math.log(1_024)), units.length - 1)
  const value = normalized / 1_024 ** exponent
  const formatted = new Intl.NumberFormat('fr-FR', {
    maximumFractionDigits: exponent === 0 ? 0 : 1,
  }).format(value)
  return `${formatted} ${units[exponent]}`
}

function usagePercentage(value: number, maximum: number) {
  if (maximum <= 0) return value > 0 ? 100 : 0
  return Math.max(0, Math.min(100, (value / maximum) * 100))
}

function countLabel(value: number, singular: string, plural: string) {
  return `${value.toLocaleString('fr-FR')} ${value === 1 ? singular : plural}`
}

type UsageMeter = {
  label: string
  value: number
  maximum: number
  formatValue: (value: number) => string
  detail: string
}

function UsageBar({ meter }: { meter: UsageMeter }) {
  const percentage = usagePercentage(meter.value, meter.maximum)
  const alert = percentage >= ALERT_THRESHOLD

  return (
    <div className="space-y-1.5">
      <Progress
        value={percentage}
        aria-label={`${meter.label} : ${meter.formatValue(meter.value)} sur ${meter.formatValue(meter.maximum)}`}
        className={cn(
          "gap-x-3 gap-y-2 [&_[data-slot='progress-track']]:h-1.5",
          alert && "[&_[data-slot='progress-indicator']]:bg-destructive",
        )}
      >
        <ProgressLabel className="text-xs font-medium text-foreground">{meter.label}</ProgressLabel>
        <ProgressValue className={cn('text-xs', alert && 'font-medium text-destructive')}>
          {() => `${meter.formatValue(meter.value)} / ${meter.formatValue(meter.maximum)}`}
        </ProgressValue>
      </Progress>
      <p className="text-[11px] text-muted-foreground">{meter.detail}</p>
    </div>
  )
}

export function StorageUsageCard({ storage }: { storage: StorageUsage }) {
  const meters: UsageMeter[] = [
    {
      label: 'Imports',
      value: storage.uploads.bytes,
      maximum: storage.uploads.max_file_bytes,
      formatValue: formatBytes,
      detail: `${countLabel(storage.uploads.files, 'fichier conservé', 'fichiers conservés')}, remplacement automatique`,
    },
    {
      label: 'Rapports',
      value: storage.reports.files,
      maximum: storage.reports.max_files,
      formatValue: (value) => countLabel(value, 'rapport', 'rapports'),
      detail: `${formatBytes(storage.reports.bytes)} utilisés`,
    },
    {
      label: 'Historique',
      value: storage.history.entries,
      maximum: storage.history.max_entries,
      formatValue: (value) => countLabel(value, 'entrée', 'entrées'),
      detail: `${formatBytes(storage.history.bytes)} dans ${countLabel(storage.history.files, 'fichier SQLite', 'fichiers SQLite')}`,
    },
  ]
  const totalBytes = storage.uploads.bytes + storage.reports.bytes + storage.history.bytes
  const alert = meters.some(
    (meter) => usagePercentage(meter.value, meter.maximum) >= ALERT_THRESHOLD,
  )

  return (
    <Card className="gap-0">
      <CardHeader className="border-b border-border pb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <HardDrive className="size-4" aria-hidden="true" />
          </span>
          <div>
            <CardTitle className="text-sm font-semibold">Capacité du workspace</CardTitle>
            <CardDescription className="mt-0.5 text-xs">
              Rétention bornée des imports, rapports et événements d’analyse
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant={alert ? 'destructive' : 'secondary'}>
            {alert ? (
              <TriangleAlert data-icon="inline-start" aria-hidden="true" />
            ) : (
              <CircleCheck data-icon="inline-start" aria-hidden="true" />
            )}
            {alert ? 'À surveiller' : 'Disponible'}
          </Badge>
        </CardAction>
      </CardHeader>

      <CardContent className="grid gap-5 pt-4 lg:grid-cols-[minmax(150px,0.65fr)_repeat(3,minmax(0,1fr))] lg:items-center">
        <div className="rounded-lg bg-muted/60 px-4 py-3">
          <p className="text-xs text-muted-foreground">Stockage utilisé</p>
          <p className="mt-1 text-xl font-semibold tracking-tight text-foreground tabular-nums">
            {formatBytes(totalBytes)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {Math.max(0, totalBytes).toLocaleString('fr-FR')} octets au total
          </p>
        </div>
        {meters.map((meter) => (
          <UsageBar key={meter.label} meter={meter} />
        ))}
      </CardContent>
    </Card>
  )
}
