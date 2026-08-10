'use client'

import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, SlidersHorizontal } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { ChartCard } from '@/components/chart-card'
import { KpiCard } from '@/components/kpi-card'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { DashboardChart } from '@/components/charts'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api, type DashboardResponse } from '@/lib/data'

type DashboardParams = { dimension?: string; metric?: string; aggregation?: string }

function metricLabel(value: string) {
  return value === '__row_count__' ? 'Nombre de lignes' : value
}

export default function DashboardPage() {
  const datasetState = useDataset()
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (params: DashboardParams = {}) => {
    setLoading(true)
    setError(null)
    try {
      const nextDashboard = await api.dashboard(params)
      setDashboard(nextDashboard)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible de calculer le dashboard.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (datasetState.overview && !datasetState.loading) queueMicrotask(() => void load())
  }, [datasetState.loading, datasetState.overview, datasetState.revision, load])

  if (datasetState.loading && !datasetState.overview) return <LoadingState />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (!datasetState.overview) return <EmptyDatasetState />
  if (loading && !dashboard) return <LoadingState label="Construction du dashboard…" />
  if (error && !dashboard) return <ErrorState message={error} retry={() => load()} />
  if (!dashboard) return <LoadingState label="Préparation des visualisations…" />

  function update(params: DashboardParams) {
    void load({
      dimension: params.dimension ?? dashboard?.dimension,
      metric: params.metric ?? dashboard?.metric,
      aggregation: params.aggregation ?? dashboard?.aggregation,
    })
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Dashboard" description="Visualisation configurable calculée par le backend sur le dataset actif">
        <Button variant="outline" size="sm" className="gap-1.5" disabled={loading} onClick={() => update({})}>
          <RefreshCw className={loading ? 'size-4 animate-spin' : 'size-4'} /> Actualiser
        </Button>
      </PageHeader>

      {error ? <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}

      <Card className="mb-4 p-5">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="size-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Configuration</h3>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Dimension
            <select
              aria-label="Dimension"
              value={dashboard.dimension}
              disabled={loading}
              onChange={(event) => update({ dimension: event.target.value })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring/30"
            >
              {dashboard.dimension_options.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Mesure
            <select
              aria-label="Mesure"
              value={dashboard.metric}
              disabled={loading}
              onChange={(event) => update({ metric: event.target.value })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring/30"
            >
              {dashboard.metric_options.map((value) => <option key={value} value={value}>{metricLabel(value)}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Agrégation
            <select
              aria-label="Agrégation"
              value={dashboard.aggregation}
              disabled={loading}
              onChange={(event) => update({ aggregation: event.target.value })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring/30"
            >
              {dashboard.aggregation_options.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </Card>

      {dashboard.kpis.length ? (
        <section aria-label="Indicateurs du dashboard" className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {dashboard.kpis.map((kpi, index) => <KpiCard key={kpi.id ?? `${kpi.label}-${index}`} kpi={kpi} />)}
        </section>
      ) : null}

      <ChartCard
        title={`${dashboard.aggregation} de ${metricLabel(dashboard.metric)} par ${dashboard.dimension}`}
        description={`${dashboard.data.length.toLocaleString('fr-FR')} groupes affichés · graphique ${dashboard.chart_type}`}
      >
        <div className={loading ? 'opacity-50 transition-opacity' : undefined}>
          <DashboardChart
            data={dashboard.data}
            chartType={dashboard.chart_type}
            dimension={dashboard.dimension}
            metric={metricLabel(dashboard.metric)}
          />
        </div>
      </ChartCard>
    </div>
  )
}
