import { BrainCircuit, CircleGauge, DatabaseZap } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { formatQuotaWindow, formatTokenCount, formatUsdEstimate } from '@/lib/ai-format'
import type { AiUsageResponse, AnalysisCacheMetrics } from '@/lib/data'

function formatBytes(bytes: number) {
  const normalized = Number.isFinite(bytes) ? Math.max(0, bytes) : 0
  if (normalized < 1_024) return `${normalized.toLocaleString('fr-FR')} octet${normalized === 1 ? '' : 's'}`
  const mebibytes = normalized / 1_024 ** 2
  if (mebibytes >= 1) {
    return `${mebibytes.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mio`
  }
  return `${(normalized / 1_024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Kio`
}

function hitRateLabel(value: number | null) {
  if (value === null) return 'En attente'
  return `${value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`
}

export function OperationsCard({
  cache,
  aiUsage,
}: {
  cache: AnalysisCacheMetrics
  aiUsage?: AiUsageResponse
}) {
  const pricedAttempts = aiUsage
    ? Math.max(0, aiUsage.totals.openai_attempts - aiUsage.totals.unpriced_attempts)
    : 0
  const usageCopy = aiUsage
    ? aiUsage.totals.total_tokens > 0
      ? `${formatTokenCount(aiUsage.totals.total_tokens)} tokens`
      : aiUsage.totals.openai_attempts > 0
        ? 'tokens non mesurés'
        : 'aucun appel OpenAI'
    : null
  const memoryCopy = typeof cache.bytes === 'number' && typeof cache.max_bytes === 'number'
    ? `${formatBytes(cache.bytes)} / ${formatBytes(cache.max_bytes)}`
    : 'Budget mémoire non exposé par ce backend'

  return (
    <Card className="gap-0" data-testid="operations-card">
      <CardHeader className="border-b border-border pb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <BrainCircuit className="size-4" aria-hidden="true" />
          </span>
          <div>
            <CardTitle className="text-sm font-semibold">Opérations de l’instance</CardTitle>
            <CardDescription className="mt-0.5 text-xs">
              Accélération des analyses et garde-fous de la démonstration
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant="secondary">Budget mémoire estimé</Badge>
        </CardAction>
      </CardHeader>

      <CardContent className={`grid gap-4 pt-4 ${aiUsage ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        <div className="rounded-lg bg-muted/60 px-4 py-3" data-testid="analysis-cache-status">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <DatabaseZap className="size-3.5" aria-hidden="true" /> Cache d’analyses Pandas / IsolationForest
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
            {cache.entries.toLocaleString('fr-FR')} / {cache.max_entries.toLocaleString('fr-FR')} entrées
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {memoryCopy} · taux de réutilisation : {hitRateLabel(cache.hit_rate)} · instance active
          </p>
        </div>

        <div className="rounded-lg bg-muted/60 px-4 py-3">
          <p className="text-xs text-muted-foreground">Calculs servis par le cache</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
            {cache.hits.toLocaleString('fr-FR')} hit{cache.hits > 1 ? 's' : ''}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {cache.misses.toLocaleString('fr-FR')} calcul{cache.misses > 1 ? 's' : ''} non présent{cache.misses > 1 ? 's' : ''} en cache
          </p>
        </div>

        {aiUsage ? (
          <div className="rounded-lg bg-muted/60 px-4 py-3">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CircleGauge className="size-3.5" aria-hidden="true" /> Quota global assistant
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">
              {aiUsage.quota.remaining.toLocaleString('fr-FR')} / {aiUsage.quota.limit.toLocaleString('fr-FR')}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {formatQuotaWindow(aiUsage.quota.window_seconds)} · {usageCopy}
              {pricedAttempts > 0
                ? ` · ${formatUsdEstimate(aiUsage.totals.estimated_cost_usd)} estimés${aiUsage.totals.unpriced_attempts > 0 ? ' · total partiel' : ''}`
                : aiUsage.totals.openai_attempts > 0
                  ? ' · coût non disponible'
                  : ''}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
