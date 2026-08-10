'use client'

import { useId, useRef } from 'react'
import { FileSpreadsheet, LoaderCircle, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDataset } from '@/components/dataset-provider'
import { cn } from '@/lib/utils'
import { SUPPORTED_UPLOAD_FORMATS_LABEL } from '@/lib/upload-constraints'

export function DatasetUploadButton({ compact = false, className }: { compact?: boolean; className?: string }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const helpId = useId()
  const { upload, uploading, uploadMaxLabel } = useDataset()

  async function onFile(file?: File) {
    if (!file) return
    try {
      await upload(file)
    } catch {
      // The provider exposes the actionable error to the whole application.
    } finally {
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="sr-only"
        aria-label={`Sélectionner un fichier ${SUPPORTED_UPLOAD_FORMATS_LABEL}`}
        aria-describedby={helpId}
        disabled={uploading}
        onChange={(event) => void onFile(event.target.files?.[0])}
      />
      <span id={helpId} className="sr-only">
        Formats acceptés : {SUPPORTED_UPLOAD_FORMATS_LABEL}. Taille maximale : {uploadMaxLabel}.
      </span>
      <Button
        type="button"
        size="sm"
        className={cn('h-9 gap-1.5', className)}
        disabled={uploading}
        aria-label={uploading ? 'Import et analyse des données en cours' : `Importer un fichier ${SUPPORTED_UPLOAD_FORMATS_LABEL}`}
        title={`Importer un fichier ${SUPPORTED_UPLOAD_FORMATS_LABEL} — ${uploadMaxLabel} maximum`}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
        ) : compact ? (
          <Upload className="size-4" aria-hidden="true" />
        ) : (
          <FileSpreadsheet className="size-4" aria-hidden="true" />
        )}
        <span className={compact ? 'hidden sm:inline' : undefined}>{uploading ? 'Import et analyse…' : 'Importer'}</span>
      </Button>
      <span className="sr-only" role="status" aria-live="polite">
        {uploading ? 'Import du fichier et analyse des données en cours.' : ''}
      </span>
    </>
  )
}
