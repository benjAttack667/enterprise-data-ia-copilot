import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { ColumnQuality } from '@/lib/data'

function ScoreMeter({ value }: { value: number }) {
  const score = Math.max(0, Math.min(100, value))
  const color = score >= 85 ? 'bg-success' : score >= 65 ? 'bg-warning' : 'bg-destructive'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${score}%` }} />
      </div>
      <span className="font-mono text-xs text-muted-foreground">{score.toFixed(0)}</span>
    </div>
  )
}

export function DataQualityTable({ columns }: { columns: ColumnQuality[] }) {
  return (
    <Card className="gap-0 overflow-hidden py-0">
      <CardHeader className="border-b border-border px-5 py-4">
        <CardTitle className="text-sm font-semibold">Qualité par colonne</CardTitle>
        <CardDescription className="text-xs">Types, complétude, cardinalité et problèmes détectés par Pandas</CardDescription>
      </CardHeader>
      {columns.length ? (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Colonne</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Manquants</TableHead>
                <TableHead>Valeurs uniques</TableHead>
                <TableHead>Score</TableHead>
                <TableHead className="pr-5">Diagnostic</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {columns.map((row) => (
                <TableRow key={row.column}>
                  <TableCell className="pl-5 font-mono text-xs font-medium text-foreground">{row.column}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{row.dtype ?? '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {(row.missing_count ?? row.missing ?? 0).toLocaleString('fr-FR')} ({(row.missing_rate ?? 0).toFixed(2)} %)
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {(row.unique_count ?? row.unique ?? 0).toLocaleString('fr-FR')}
                  </TableCell>
                  <TableCell><ScoreMeter value={row.score ?? 0} /></TableCell>
                  <TableCell className="max-w-72 whitespace-normal pr-5 text-xs text-muted-foreground">
                    {row.issues?.length ? row.issues.join(' · ') : row.action ?? row.status ?? 'Aucun problème détecté'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="p-6 text-sm text-muted-foreground">Aucune colonne à analyser.</p>
      )}
    </Card>
  )
}
