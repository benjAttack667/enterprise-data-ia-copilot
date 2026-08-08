'use client'

import { AlertCircle, RefreshCw, Radar, Sigma, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api } from '@/lib/data'
import { useApiResource } from '@/lib/use-api-resource'

function flattenRow(row: Record<string, unknown>) {
  const values = row.values
  if (values && typeof values === 'object' && !Array.isArray(values)) {
    const metadata = { ...row }
    delete metadata.values
    return { ...metadata, ...(values as Record<string, unknown>) }
  }
  return row
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString('fr-FR', { maximumFractionDigits: 4 })
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default function AnomaliesPage() {
  const datasetState = useDataset()
  const resource = useApiResource(api.anomalies, {
    enabled: Boolean(datasetState.overview) && !datasetState.loading,
    revision: datasetState.revision,
  })

  if (datasetState.loading && !datasetState.overview) return <LoadingState />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (!datasetState.overview) return <EmptyDatasetState />
  if (resource.loading && !resource.data) return <LoadingState label="Exécution d’IsolationForest…" />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.reload} />
  if (!resource.data) return <LoadingState label="Préparation de la détection…" />

  const rows = resource.data.rows.map(flattenRow)
  const allColumns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
  const columns = allColumns.slice(0, 10)
  const stats = [
    { label: 'Anomalies détectées', value: resource.data.count.toLocaleString('fr-FR'), icon: Radar, tone: 'text-destructive', bg: 'bg-destructive/10' },
    { label: 'Taux d’anomalies', value: `${resource.data.rate.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`, icon: TrendingUp, tone: 'text-warning', bg: 'bg-warning/15' },
    { label: 'Variables numériques', value: String(resource.data.numeric_columns?.length ?? 0), icon: Sigma, tone: 'text-primary', bg: 'bg-primary/10' },
  ]

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Détection d’anomalies" description={`IsolationForest sur le dataset actif${resource.data.method ? ` · ${resource.data.method}` : ''}`}>
        <Button variant="outline" size="sm" className="gap-1.5" disabled={resource.loading} onClick={() => void resource.reload()}>
          <RefreshCw className={resource.loading ? 'size-4 animate-spin' : 'size-4'} /> Relancer
        </Button>
      </PageHeader>

      {resource.data.applicable === false ? (
        <Card className="flex min-h-64 items-center justify-center border-warning/30 p-8">
          <div className="max-w-xl text-center">
            <AlertCircle className="mx-auto size-9 text-warning" />
            <p className="mt-4 text-sm font-semibold text-foreground">Détection non applicable</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {resource.data.message ?? 'Le dataset ne contient pas assez de données numériques exploitables.'}
            </p>
          </div>
        </Card>
      ) : (
        <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label} className="flex flex-row items-center gap-3 p-4">
              <span className={`flex size-10 items-center justify-center rounded-lg ${stat.bg}`}><Icon className={`size-5 ${stat.tone}`} /></span>
              <div><p className="font-mono text-xl font-semibold text-foreground">{stat.value}</p><p className="text-xs text-muted-foreground">{stat.label}</p></div>
            </Card>
          )
        })}
      </div>

      <Card className="mt-4 gap-0 overflow-hidden py-0">
        <CardHeader className="border-b border-border px-5 py-4">
          <CardTitle className="text-sm font-semibold">Lignes signalées</CardTitle>
          <CardDescription className="text-xs">
            {rows.length ? `${rows.length.toLocaleString('fr-FR')} lignes retournées${allColumns.length > columns.length ? ` · ${columns.length} colonnes affichées sur ${allColumns.length}` : ''}` : 'Aucune anomalie détectée'}
          </CardDescription>
        </CardHeader>
        {rows.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">{columns.map((column) => <TableHead key={column} className="whitespace-nowrap first:pl-5 last:pr-5">{column}</TableHead>)}</TableRow></TableHeader>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow key={index}>{columns.map((column) => <TableCell key={column} className="max-w-56 truncate whitespace-nowrap font-mono text-xs text-muted-foreground first:pl-5 last:pr-5" title={displayValue(row[column])}>{displayValue(row[column])}</TableCell>)}</TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="p-8 text-center text-sm text-muted-foreground">Le modèle n’a signalé aucune ligne atypique.</div>
        )}
      </Card>
        </>
      )}
    </div>
  )
}
