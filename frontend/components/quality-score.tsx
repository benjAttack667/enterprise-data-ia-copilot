import { Card } from '@/components/ui/card'

const labels: Record<string, string> = {
  row_count: 'Lignes analysées',
  column_count: 'Colonnes',
  missing_count: 'Valeurs manquantes',
  missing_rate: 'Taux manquant',
  duplicate_count: 'Doublons',
  duplicate_rate: 'Taux de doublons',
  outlier_count: 'Valeurs atypiques',
  outlier_rate: 'Taux atypique',
  invalid_numeric_count: 'Valeurs non finies',
  strict_duplicate_count: 'Doublons stricts',
  identifier_duplicate_count: 'Identifiants répétés',
  flagged_duplicate_count: 'Doublons signalés',
}

function displayValue(key: string, value: number) {
  if (key.endsWith('_rate')) return `${value.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`
  return value.toLocaleString('fr-FR')
}

export function QualityScore({ score, summary }: { score: number; summary?: Record<string, number> }) {
  const safeScore = Math.max(0, Math.min(100, score))
  const circumference = 2 * Math.PI * 52
  const offset = circumference - (safeScore / 100) * circumference
  const stats = Object.entries(summary ?? {}).filter(([, value]) => Number.isFinite(value))

  return (
    <Card className="flex flex-col items-center gap-6 p-6 sm:flex-row sm:items-center">
      <div className="relative flex size-36 shrink-0 items-center justify-center">
        <svg viewBox="0 0 120 120" className="size-36 -rotate-90" aria-hidden>
          <circle cx="60" cy="60" r="52" fill="none" stroke="var(--muted)" strokeWidth="12" />
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke={safeScore >= 80 ? 'var(--success)' : safeScore >= 60 ? 'var(--warning)' : 'var(--destructive)'}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="font-mono text-3xl font-semibold text-foreground">{Math.round(safeScore)}</span>
          <span className="text-xs text-muted-foreground">sur 100</span>
        </div>
      </div>

      <div className="w-full flex-1">
        <p className="text-sm font-semibold text-foreground">Score global de qualité</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Calculé par le moteur d’audit sur le dataset actif</p>
        {stats.length ? (
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {stats.map(([key, value]) => (
              <div key={key} className="rounded-lg bg-muted/60 p-3">
                <dt className="text-xs text-muted-foreground">{labels[key] ?? key}</dt>
                <dd className="mt-1 font-mono text-sm font-semibold text-foreground">{displayValue(key, value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </Card>
  )
}
