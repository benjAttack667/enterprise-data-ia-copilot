'use client'

import { useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { FileSpreadsheet, LoaderCircle } from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SheetSelectionRequest } from '@/components/dataset-provider'
import { formatUploadSizeLabel } from '@/lib/upload-constraints'

type SheetSelectionDialogProps = {
  selection: SheetSelectionRequest
  uploading: boolean
  error: string | null
  onConfirm: (sheetName: string) => Promise<void>
  onCancel: () => void
}

export function SheetSelectionDialog({
  selection,
  uploading,
  error,
  onConfirm,
  onCancel,
}: SheetSelectionDialogProps) {
  const [selectedSheet, setSelectedSheet] = useState('')

  async function confirmSelection() {
    if (!selectedSheet || uploading) return
    try {
      await onConfirm(selectedSheet)
    } catch {
      // The actionable error stays visible in this dialog and in the global banner.
    }
  }

  return (
    <Dialog.Root
      open
      disablePointerDismissal={uploading}
      onOpenChange={(open) => {
        if (!open && !uploading) onCancel()
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-slate-950/55 backdrop-blur-[2px] transition-opacity duration-150 data-closed:opacity-0 data-open:opacity-100" />
        <Dialog.Viewport className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4">
          <Dialog.Popup
            data-testid="sheet-selection-dialog"
            className="w-full max-w-md rounded-2xl border border-border bg-card p-5 text-card-foreground shadow-2xl outline-none transition duration-150 data-closed:scale-95 data-closed:opacity-0 data-open:scale-100 data-open:opacity-100 sm:p-6"
          >
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <FileSpreadsheet className="size-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <Dialog.Title className="text-base font-semibold">Choisir une feuille Excel</Dialog.Title>
                <Dialog.Description className="mt-1 text-sm leading-5 text-muted-foreground">
                  Ce classeur contient plusieurs feuilles. Choisissez celle que le Copilot doit analyser.
                </Dialog.Description>
              </div>
            </div>

            <div className="mt-5 rounded-xl border border-border bg-muted/45 px-3 py-2.5">
              <p className="truncate text-sm font-medium" title={selection.fileName}>{selection.fileName}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {formatUploadSizeLabel(selection.fileSize)} · {selection.sheets.length} feuilles disponibles
              </p>
            </div>

            <label className="mt-5 block text-sm font-medium" htmlFor="excel-sheet-selection">
              Feuille à importer
            </label>
            <Select
              id="excel-sheet-selection"
              items={selection.sheets.map((sheet) => ({ label: sheet, value: sheet }))}
              value={selectedSheet}
              disabled={uploading}
              onValueChange={(value) => setSelectedSheet(value ?? '')}
            >
              <SelectTrigger
                className="mt-2 h-10 w-full"
                aria-label="Feuille Excel"
                data-testid="sheet-selection-select"
              >
                <SelectValue placeholder="Sélectionner une feuille" />
              </SelectTrigger>
              <SelectContent align="start">
                {selection.sheets.map((sheet) => (
                  <SelectItem key={sheet} value={sheet}>{sheet}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {error ? (
              <p role="alert" className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            ) : null}

            <p className="mt-4 text-xs leading-5 text-muted-foreground">
              Le fichier n&apos;est ni activé ni conservé avant votre confirmation.
            </p>

            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Dialog.Close
                type="button"
                disabled={uploading}
                className={buttonVariants({ variant: 'outline', size: 'lg' })}
              >
                Annuler
              </Dialog.Close>
              <Button
                type="button"
                size="lg"
                data-testid="sheet-selection-confirm"
                disabled={!selectedSheet || uploading}
                onClick={() => void confirmSelection()}
              >
                {uploading ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : null}
                {uploading ? 'Import et analyse…' : 'Analyser cette feuille'}
              </Button>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
