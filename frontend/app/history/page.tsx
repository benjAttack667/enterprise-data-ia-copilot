'use client'

import { Clock3, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api } from '@/lib/data'
import { useApiResource } from '@/lib/use-api-resource'

function formatTimestamp(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
}

function formatDetails(value?: string | Record<string, unknown>) {
  if (!value) return '—'
  if (typeof value === 'string') return value
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${typeof item === 'object' ? JSON.stringify(item) : String(item)}`)
    .join(' · ')
}

export default function HistoryPage() {
  const datasetState = useDataset()
  const resource = useApiResource(api.history, { enabled: !datasetState.loading, revision: datasetState.revision })

  if (datasetState.loading || (resource.loading && !resource.data)) return <LoadingState label="Chargement de l’historique…" />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.reload} />

  const items = resource.data?.items ?? []
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Historique" description="Journal SQLite des imports, analyses, questions IA et rapports">
        <Button variant="outline" size="sm" className="gap-1.5" disabled={resource.loading} onClick={() => void resource.reload()}>
          <RefreshCw className={resource.loading ? 'size-4 animate-spin' : 'size-4'} /> Actualiser
        </Button>
      </PageHeader>

      <Card className="gap-0 overflow-hidden py-0">
        <CardHeader className="border-b border-border px-5 py-4">
          <CardTitle className="text-sm font-semibold">Journal d’activité</CardTitle>
          <CardDescription className="text-xs">{items.length.toLocaleString('fr-FR')} événements enregistrés</CardDescription>
        </CardHeader>
        {items.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-5">Action</TableHead>
                  <TableHead>Dataset</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Détails</TableHead>
                  <TableHead className="pr-5">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="pl-5 text-sm font-medium text-foreground">{entry.action ?? entry.event_type ?? 'Événement'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{entry.dataset_name ?? entry.dataset ?? '—'}</TableCell>
                    <TableCell>
                      <Badge variant={entry.status === 'failed' ? 'destructive' : 'outline'}>
                        {entry.status ?? 'completed'}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-md whitespace-normal text-xs text-muted-foreground">{formatDetails(entry.details)}</TableCell>
                    <TableCell className="whitespace-nowrap pr-5 font-mono text-xs text-muted-foreground">{formatTimestamp(entry.created_at ?? entry.timestamp)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <Clock3 className="size-8 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium text-foreground">Aucune activité enregistrée</p>
            <p className="mt-1 text-xs text-muted-foreground">Les prochaines opérations apparaîtront ici.</p>
          </div>
        )}
      </Card>
    </div>
  )
}
