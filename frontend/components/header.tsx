'use client'

import { CheckCircle2, Database, LoaderCircle, Menu, WifiOff } from 'lucide-react'
import { DatasetUploadButton } from '@/components/dataset-upload'
import { useDataset } from '@/components/dataset-provider'
import { LogoutButton } from '@/components/logout-button'
import { Badge } from '@/components/ui/badge'

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { overview, loading, uploading, error, uploadError } = useDataset()
  const dataset = overview?.dataset
  const visibleError = uploadError ?? error
  const datasetDetails = dataset
    ? [
        `${dataset.rows.toLocaleString('fr-FR')} lignes`,
        `${dataset.columns} colonnes`,
        dataset.selected_sheet ? `Feuille ${dataset.selected_sheet}` : null,
      ].filter(Boolean).join(' · ')
    : 'Import requis'

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/90 px-4 backdrop-blur lg:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted lg:hidden"
        aria-label="Ouvrir la navigation"
      >
        <Menu className="size-5" />
      </button>

      <div className="hidden min-w-0 lg:block">
        <h1 className="truncate text-sm font-semibold text-foreground">Enterprise Data &amp; IA Copilot</h1>
        <p className="truncate text-xs text-muted-foreground">Qualité, anomalies et analyses IA</p>
      </div>

      <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-3">
        <div className="hidden min-w-0 items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 sm:flex sm:max-w-64">
          <Database className="size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5">
              <p className="truncate text-xs font-medium text-foreground">{dataset?.name ?? 'Aucun dataset'}</p>
              {overview?.dataset_recovery?.status === 'restored' ? (
                <Badge
                  variant="outline"
                  data-testid="dataset-recovery-badge"
                  title={overview.dataset_recovery.message ?? 'Dataset restauré depuis le stockage persistant'}
                  className="h-4 border-success/25 bg-success/10 px-1.5 text-[10px] text-success"
                >
                  Restauré
                </Badge>
              ) : null}
            </div>
            <p className="truncate text-[11px] text-muted-foreground" title={datasetDetails}>
              {datasetDetails}
            </p>
          </div>
        </div>

        <DatasetUploadButton compact />

        <LogoutButton />

        <span
          title={visibleError ?? undefined}
          className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset md:inline-flex ${
            visibleError
              ? 'bg-destructive/10 text-destructive ring-destructive/20'
              : loading || uploading
                ? 'bg-primary/10 text-primary ring-primary/20'
                : dataset
                  ? 'bg-success/10 text-success ring-success/20'
                  : 'bg-muted text-muted-foreground ring-border'
          }`}
        >
          {visibleError ? (
            <WifiOff className="size-3.5" />
          ) : loading || uploading ? (
            <LoaderCircle className="size-3.5 animate-spin" />
          ) : dataset ? (
            <CheckCircle2 className="size-3.5" />
          ) : (
            <Database className="size-3.5" />
          )}
          {visibleError ? 'Erreur' : loading || uploading ? 'Analyse…' : dataset ? 'Analyse prête' : 'Dataset requis'}
        </span>
      </div>
    </header>
  )
}
