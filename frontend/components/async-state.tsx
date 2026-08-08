'use client'

import { AlertCircle, Database, LoaderCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { DatasetUploadButton } from '@/components/dataset-upload'

export function LoadingState({ label = 'Analyse des données…' }: { label?: string }) {
  return (
    <Card className="flex min-h-64 items-center justify-center p-8">
      <div className="text-center">
        <LoaderCircle className="mx-auto size-7 animate-spin text-primary" />
        <p className="mt-3 text-sm font-medium text-foreground">{label}</p>
      </div>
    </Card>
  )
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void | Promise<void> }) {
  return (
    <Card className="flex min-h-64 items-center justify-center border-destructive/20 p-8">
      <div className="max-w-lg text-center">
        <AlertCircle className="mx-auto size-8 text-destructive" />
        <p className="mt-3 text-sm font-semibold text-foreground">Chargement impossible</p>
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
        {retry ? (
          <Button type="button" variant="outline" size="sm" className="mt-4 gap-1.5" onClick={() => void retry()}>
            <RefreshCw className="size-4" /> Réessayer
          </Button>
        ) : null}
      </div>
    </Card>
  )
}

export function EmptyDatasetState() {
  return (
    <Card className="flex min-h-72 items-center justify-center border-dashed p-8">
      <div className="max-w-md text-center">
        <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Database className="size-6" />
        </span>
        <p className="mt-4 text-sm font-semibold text-foreground">Aucun dataset actif</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Importez un fichier CSV ou Excel pour lancer l’analyse Pandas et alimenter toutes les pages.
        </p>
        <DatasetUploadButton className="mt-4" />
      </div>
    </Card>
  )
}
