import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatNullableNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ColumnQuality } from '@/lib/data'

const semanticTypeLabels: Record<string, string> = {
  boolean: 'Booléen',
  categorical: 'Catégorie',
  date: 'Date',
  datetime: 'Date et heure',
  decimal: 'Nombre décimal',
  email: 'E-mail',
  empty: 'Colonne vide',
  float: 'Nombre décimal',
  identifier: 'Identifiant',
  integer: 'Nombre entier',
  numeric: 'Numérique',
  number: 'Numérique',
  text: 'Texte',
}

const issueLabels: Record<string, string> = {
  ambiguous_dates: 'Dates ambiguës',
  empty_column: 'Colonne vide',
  invalid_dates: 'Dates invalides',
  invalid_numeric_values: 'Nombres invalides',
  invalid_semantic_values: 'Valeurs invalides',
  missing_values: 'Valeurs manquantes',
  mixed_types: 'Types mixtes',
  non_finite_values: 'Valeurs non finies',
  outliers: 'Valeurs atypiques',
}

const statusLabels: Record<string, string> = {
  critical: 'Action requise',
  healthy: 'Aucun problème détecté',
  warning: 'À surveiller',
}

function semanticType(row: ColumnQuality) {
  const value = row.inferred_type ?? row.semantic_type
  if (!value) return null
  return semanticTypeLabels[value.toLowerCase()] ?? value.replaceAll('_', ' ')
}

function hasSemanticParseRate(row: ColumnQuality) {
  const value = (row.inferred_type ?? row.semantic_type)?.toLowerCase()
  return Boolean(value && ['date', 'datetime', 'decimal', 'float', 'number', 'numeric'].includes(value))
}

function missingValue(row: ColumnQuality) {
  const count = row.missing_count ?? row.missing
  const rate = row.missing_rate
  const formattedCount = formatNullableNumber(count, 0)
  const formattedRate = formatNullableNumber(rate, 2)
  if (formattedCount === '—') return formattedRate === '—' ? '—' : `${formattedRate} %`
  return formattedRate === '—' ? formattedCount : `${formattedCount} (${formattedRate} %)`
}

function ScoreMeter({ value }: { value: number | null | undefined }) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return <span className="font-mono text-xs text-muted-foreground">—</span>
  }
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
        <CardDescription className="text-xs">Types sémantiques, complétude, validité et cardinalité détectés par Pandas</CardDescription>
      </CardHeader>
      {columns.length ? (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Colonne</TableHead>
                <TableHead>Type sémantique</TableHead>
                <TableHead>Manquants</TableHead>
                <TableHead>Invalides</TableHead>
                <TableHead>Valeurs uniques</TableHead>
                <TableHead>Score</TableHead>
                <TableHead className="pr-5">Diagnostic</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {columns.map((row) => (
                <TableRow key={row.column}>
                  <TableCell className="pl-5 font-mono text-xs font-medium text-foreground">{row.column}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{semanticType(row) ?? row.dtype ?? '—'}</span>
                    {semanticType(row) && row.dtype ? <span className="mt-0.5 block font-mono text-[11px]">Pandas : {row.dtype}</span> : null}
                    {hasSemanticParseRate(row) && typeof row.parse_rate === 'number' && Number.isFinite(row.parse_rate) ? (
                      <span className="mt-0.5 block text-[11px]">Validité : {formatNullableNumber(row.parse_rate, 2)} %</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {missingValue(row)}
                    {typeof row.blank_count === 'number' && row.blank_count > 0 ? (
                      <span className="mt-0.5 block text-[11px]">Chaînes vides : {formatNullableNumber(row.blank_count, 0)}</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatNullableNumber(row.invalid_count ?? row.invalid_numeric_count, 0)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatNullableNumber(row.unique_count ?? row.unique, 0)}
                  </TableCell>
                  <TableCell><ScoreMeter value={row.score} /></TableCell>
                  <TableCell className="max-w-72 whitespace-normal pr-5 text-xs text-muted-foreground">
                    {row.issues?.length
                      ? row.issues.map((issue) => issueLabels[issue] ?? issue.replaceAll('_', ' ')).join(' · ')
                      : row.action ?? (row.status ? statusLabels[row.status] ?? row.status : 'Aucun problème détecté')}
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
