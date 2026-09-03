'use client'

import { Bot, CircleGauge, Coins, LoaderCircle, TriangleAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  formatQuotaWindow,
  formatTokenCount,
  formatUsdEstimate,
} from '@/lib/ai-format'
import type { AiProvider, AiResponse, AiUsageResponse } from '@/lib/data'

export function ProviderBadge({ provider }: { provider: AiProvider }) {
  return (
    <Badge variant={provider === 'openai' ? 'default' : 'secondary'}>
      {provider === 'openai' ? 'OpenAI' : 'Fallback local'}
    </Badge>
  )
}

function measuredUsageCopy(response: AiResponse) {
  const usage = response.usage!
  const tokens = `${formatTokenCount(usage.total_tokens ?? 0)} tokens`
  const cached = (usage.cached_input_tokens ?? 0) > 0
    ? `, dont ${formatTokenCount(usage.cached_input_tokens ?? 0)} en cache`
    : ''
  const cost = usage.pricing_status === 'estimated' && usage.estimated_cost_usd !== null
    ? ` · coût estimé ${formatUsdEstimate(usage.estimated_cost_usd)}`
    : ' · tarif non configuré pour ce modèle'
  const model = usage.model ? `${usage.model} · ` : ''
  const prefix = response.provider === 'openai'
    ? model
    : `Fallback local après une tentative OpenAI${usage.model ? ` (${usage.model})` : ''} · `
  return `${prefix}${tokens}${cached}${cost}`
}

export function AiResponseMetadata({ response }: { response: AiResponse }) {
  let copy: string
  if (!response.usage) {
    copy = 'Télémétrie non disponible sur cette version du backend'
  } else if (response.usage.status === 'measured') {
    copy = measuredUsageCopy(response)
  } else if (
    response.usage.status === 'not_applicable' &&
    response.usage.fallback_reason === 'missing_api_key'
  ) {
    copy = 'Traitement local · aucun appel OpenAI'
  } else if (!response.usage.openai_request_attempted) {
    copy = 'Traitement local · fournisseur OpenAI indisponible avant l’appel'
  } else if (response.provider === 'openai') {
    copy = 'Réponse OpenAI · tokens et coût indisponibles'
  } else {
    copy = 'Traitement local après une tentative OpenAI · tokens et coût indisponibles'
  }

  return (
    <div
      data-testid="ai-response-metadata"
      className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground"
    >
      <ProviderBadge provider={response.provider} />
      <span>{copy}</span>
    </div>
  )
}

function pricedAttempts(data: AiUsageResponse) {
  return Math.max(0, data.totals.openai_attempts - data.totals.unpriced_attempts)
}

export function AiTelemetryCard({
  data,
  loading,
  error,
}: {
  data: AiUsageResponse | null
  loading: boolean
  error: string | null
}) {
  if (!data) {
    const waiting = loading || !error
    return (
      <Card size="sm" className="mb-4" data-testid="ai-telemetry-card">
        <CardContent
          role={waiting ? 'status' : 'alert'}
          className="flex min-h-20 items-center gap-2 text-xs text-muted-foreground"
        >
          {waiting ? (
            <>
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              Chargement du quota et de la télémétrie IA…
            </>
          ) : (
            <>
              <TriangleAlert className="size-4 text-amber-600" aria-hidden="true" />
              {error ?? 'Télémétrie IA temporairement indisponible.'}
            </>
          )}
        </CardContent>
      </Card>
    )
  }

  const quota = data.quota
  const priced = pricedAttempts(data)
  const quotaAlert = quota.remaining === 0
  const tokenTotal = data.totals.total_tokens > 0
    ? formatTokenCount(data.totals.total_tokens)
    : data.totals.openai_attempts > 0
      ? 'Non mesurés'
      : 'Aucun appel'

  return (
    <Card size="sm" className="mb-4 gap-0" data-testid="ai-telemetry-card">
      <CardHeader className="border-b border-border pb-3">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Bot className="size-4" aria-hidden="true" />
          </span>
          <div>
            <CardTitle className="text-sm font-semibold">Pilotage de l’assistant</CardTitle>
            <CardDescription className="text-xs">
              {data.provider
                ? data.provider.configured
                  ? `OpenAI configuré · ${data.provider.model}`
                  : 'Fallback local par défaut · aucune clé OpenAI configurée'
                : 'Quota global de la démo et consommation OpenAI mesurée'}
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant={quotaAlert ? 'destructive' : 'secondary'}>
            {quota.remaining.toLocaleString('fr-FR')} / {quota.limit.toLocaleString('fr-FR')} disponibles
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-3 pt-3 sm:grid-cols-3">
        <div className="rounded-lg bg-muted/60 px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <CircleGauge className="size-3.5" aria-hidden="true" /> Quota global
          </p>
          <p className="mt-1 text-base font-semibold tabular-nums text-foreground">
            {quota.remaining.toLocaleString('fr-FR')} requête{quota.remaining === 1 ? '' : 's'}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {quotaAlert && quota.next_slot_after_seconds > 0
              ? `Prochain créneau dans ${formatQuotaWindow(quota.next_slot_after_seconds)}`
              : `Fenêtre glissante de ${formatQuotaWindow(quota.window_seconds)}`}
            {' · instance active'}
          </p>
        </div>
        <div className="rounded-lg bg-muted/60 px-3 py-2.5">
          <p className="text-[11px] text-muted-foreground">Tokens OpenAI retenus</p>
          <p className="mt-1 text-base font-semibold tabular-nums text-foreground">
            {tokenTotal}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {data.totals.fallback_responses.toLocaleString('fr-FR')} réponse{data.totals.fallback_responses > 1 ? 's' : ''} locale{data.totals.fallback_responses > 1 ? 's' : ''} · {data.retention.entries.toLocaleString('fr-FR')} / {data.retention.max_entries.toLocaleString('fr-FR')} événements retenus
          </p>
        </div>
        <div className="rounded-lg bg-muted/60 px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Coins className="size-3.5" aria-hidden="true" /> Coût des appels mesurés
          </p>
          <p className="mt-1 text-base font-semibold tabular-nums text-foreground">
            {data.totals.openai_attempts === 0
              ? 'Aucun appel'
              : priced > 0
                ? formatUsdEstimate(data.totals.estimated_cost_usd)
                : 'Non estimable'}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {data.totals.unpriced_attempts > 0
              ? `${data.totals.unpriced_attempts.toLocaleString('fr-FR')} tentative${data.totals.unpriced_attempts > 1 ? 's' : ''} sans estimation · total partiel`
              : 'Estimation applicative, pas une facture OpenAI'}
          </p>
        </div>
      </CardContent>
      {error ? (
        <div className="border-t border-border px-3 py-2 text-[11px] text-amber-700">
          Dernière mesure conservée · actualisation impossible : {error}
        </div>
      ) : null}
    </Card>
  )
}
