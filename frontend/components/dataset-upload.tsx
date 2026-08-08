'use client'

import { useRef } from 'react'
import { FileSpreadsheet, LoaderCircle, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDataset } from '@/components/dataset-provider'
import { cn } from '@/lib/utils'

export function DatasetUploadButton({ compact = false, className }: { compact?: boolean; className?: string }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { upload, uploading } = useDataset()

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
        onChange={(event) => void onFile(event.target.files?.[0])}
      />
      <Button
        type="button"
        size="sm"
        className={cn('h-9 gap-1.5', className)}
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? (
          <LoaderCircle className="size-4 animate-spin" />
        ) : compact ? (
          <Upload className="size-4" />
        ) : (
          <FileSpreadsheet className="size-4" />
        )}
        <span className={compact ? 'hidden sm:inline' : undefined}>{uploading ? 'Import…' : 'Importer'}</span>
      </Button>
    </>
  )
}
