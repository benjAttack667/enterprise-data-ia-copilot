'use client'

import { AlertCircle, RefreshCw, Radar, Sigma, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api } from '@/lib/data'
import { formatDataValue, formatNullableNumber } from '@/lib/format'
import { useApiResource } from '@/lib/use-api-resource'

const RESERVED_METADATA = new Set([
  'anomaly_score',
  'contributing_columns',
  'row_index',
  'values',
])

type AnomalyRow = {
  key: string
  rowIndex: unknown
  anomalyScore: unknown
  contributors: string[]
  values: Record<string, unknown>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeRow(row: Record<string, unknown>, index: number): AnomalyRow {
  const nestedValues = isRecord(row.values)
    ? row.values
    : Object.fromEntries(
        Object.entries(row).filter(([key]) => !RESERVED_METADATA.has(key)),
      )
  const contributors = Array.isArray(row.contributing_columns)
    ? row.contributing_columns.filter((value): value is string => typeof value === 'string')
    : []

  return {
    key: `${String(row.row_index ?? 'row')}-${index}`,
    rowIndex: row.row_index,
    anomalyScore: row.anomaly_score,
    contributors,
    // Les valeurs métier restent dans leur propre espace de noms. Une colonne
    // appelée "row_index" ou "anomaly_score" ne peut donc plus écraser le modèle.
    values: nestedValues,
  }
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
  if (resource.error && !resource.data) return <ErrorState message={resource.error} retry={resource.reload} />
  if (!resource.data) return <LoadingState label="Préparation de la détection…" />

  const rows = resource.data.rows.map(normalizeRow)
  const allColumns = Array.from(new Set(rows.flatMap((row) => Object.keys(row.values))))
  const contributorColumns = Array.from(
    new Set(rows.flatMap((row) => row.contributors)),
  ).filter((column) => allColumns.includes(column))
  const columns = [
    ...contributorColumns,
    ...allColumns.filter((column) => !contributorColumns.includes(column)),
  ].slice(0, 7)
  const contributorSet = new Set(contributorColumns)
  const totalCount = resource.data.total_count ?? resource.data.count
  const returnedCount = resource.data.returned_count ?? rows.length
  const truncated = resource.data.truncated ?? returnedCount < totalCount
  const stats = [
    { label: 'Lignes atypiques signalées', value: formatNullableNumber(totalCount, 0), icon: Radar, tone: 'text-destructive', bg: 'bg-destructive/10' },
    { label: 'Part du dataset', value: `${formatNullableNumber(resource.data.rate, 2)} %`, icon: TrendingUp, tone: 'text-warning', bg: 'bg-warning/15' },
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

      <div className="mt-4 flex gap-3 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-muted-foreground" role="note">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-primary" />
        <div>
          <p>{resource.data.message ?? 'Les lignes signalées sont à examiner : elles ne sont pas automatiquement erronées.'}</p>
          {resource.data.excluded_identifier_columns?.length ? (
            <p className="mt-1 text-xs">Identifiants exclus du modèle : {resource.data.excluded_identifier_columns.join(', ')}.</p>
          ) : null}
        </div>
      </div>

      <Card className="mt-4 gap-0 overflow-hidden py-0">
        <CardHeader className="border-b border-border px-5 py-4">
          <CardTitle className="text-sm font-semibold">Lignes signalées</CardTitle>
          <CardDescription className="text-xs">
            {rows.length
              ? `${formatNullableNumber(returnedCount, 0)} ligne(s) affichée(s)${truncated ? ` sur ${formatNullableNumber(totalCount, 0)} signalée(s)` : ''}${allColumns.length > columns.length ? ` · ${columns.length} colonnes métier affichées sur ${allColumns.length}` : ''}`
              : 'Aucune ligne atypique signalée'}
          </CardDescription>
        </CardHeader>
        {rows.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="whitespace-nowrap pl-5">Ligne</TableHead>
                  <TableHead className="whitespace-nowrap">Score d’atypie</TableHead>
                  <TableHead className="whitespace-nowrap">Variables contributrices</TableHead>
                  {columns.map((column) => (
                    <TableHead
                      key={column}
                      className="whitespace-nowrap last:pr-5"
                      title={contributorSet.has(column) ? 'Variable contributrice prioritaire' : undefined}
                    >
                      {column}{contributorSet.has(column) ? ' · facteur' : ''}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell className="whitespace-nowrap pl-5 font-mono text-xs font-medium text-foreground">{formatDataValue(row.rowIndex)}</TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{formatDataValue(row.anomalyScore)}</TableCell>
                    <TableCell className="max-w-64 truncate whitespace-nowrap text-xs text-muted-foreground" title={row.contributors.join(', ')}>
                      {row.contributors.length ? row.contributors.join(', ') : '—'}
                    </TableCell>
                    {columns.map((column) => {
                      const value = formatDataValue(row.values[column])
                      return (
                        <TableCell key={column} className="max-w-56 truncate whitespace-nowrap font-mono text-xs text-muted-foreground last:pr-5" title={value}>
                          {value}
                        </TableCell>
                      )
                    })}
                  </TableRow>
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
