'use client'

import { AlertTriangle, Copy, RefreshCw, ScanSearch } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { QualityScore } from '@/components/quality-score'
import { DataQualityTable } from '@/components/data-quality-table'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api } from '@/lib/data'
import { useApiResource } from '@/lib/use-api-resource'

export default function DataQualityPage() {
  const datasetState = useDataset()
  const enabled = Boolean(datasetState.overview) && !datasetState.loading
  const resource = useApiResource(api.dataQuality, { enabled, revision: datasetState.revision })

  if (datasetState.loading && !datasetState.overview) return <LoadingState />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (!datasetState.overview) return <EmptyDatasetState />
  if (resource.loading && !resource.data) return <LoadingState label="Audit Data Quality en cours…" />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.reload} />
  if (!resource.data) return <LoadingState label="Préparation de l’audit…" />

  const summary = typeof resource.data.summary === 'string' ? {} : resource.data.summary
  const stats = [
    { label: 'Valeurs manquantes', value: summary.missing_count ?? 0, icon: AlertTriangle, tone: 'text-warning', bg: 'bg-warning/15' },
    { label: 'Doublons', value: summary.duplicate_count ?? 0, icon: Copy, tone: 'text-destructive', bg: 'bg-destructive/10' },
    { label: 'Valeurs atypiques', value: summary.outlier_count ?? 0, icon: ScanSearch, tone: 'text-primary', bg: 'bg-primary/10' },
  ]

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Qualité des données" description="Audit réel de complétude, unicité et cohérence du dataset actif">
        <Button variant="outline" size="sm" className="gap-1.5" disabled={resource.loading} onClick={() => void resource.reload()}>
          <RefreshCw className={resource.loading ? 'size-4 animate-spin' : 'size-4'} />
          Relancer l’audit
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <QualityScore score={resource.data.score} summary={summary} />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-1">
          {stats.map((stat) => {
            const Icon = stat.icon
            return (
              <Card key={stat.label} className="flex flex-row items-center gap-3 p-4">
                <span className={`flex size-10 items-center justify-center rounded-lg ${stat.bg}`}>
                  <Icon className={`size-5 ${stat.tone}`} />
                </span>
                <div>
                  <p className="font-mono text-xl font-semibold text-foreground">{stat.value.toLocaleString('fr-FR')}</p>
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                </div>
              </Card>
            )
          })}
        </div>
      </div>

      {resource.data.problems.length || resource.data.recommendations.length ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-foreground">Problèmes détectés</h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {resource.data.problems.map((problem, index) => (
                <li key={index} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-destructive" />{typeof problem === 'string' ? problem : problem.message ?? problem.title ?? problem.detail}</li>
              ))}
              {!resource.data.problems.length ? <li>Aucun problème bloquant.</li> : null}
            </ul>
          </Card>
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-foreground">Actions recommandées</h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {resource.data.recommendations.map((item, index) => {
                const text = typeof item === 'string' ? item : `${item.title}${item.detail ? ` — ${item.detail}` : ''}`
                return <li key={index} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />{text}</li>
              })}
              {!resource.data.recommendations.length ? <li>Aucune action prioritaire.</li> : null}
            </ul>
          </Card>
        </div>
      ) : null}

      <div className="mt-4"><DataQualityTable columns={resource.data.columns} /></div>
    </div>
  )
}
