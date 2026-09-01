'use client'

import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { AlertTriangle } from 'lucide-react'
import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'
import { DatasetProvider, useDataset } from '@/components/dataset-provider'
import { SheetSelectionDialog } from '@/components/sheet-selection-dialog'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const pathname = usePathname()

  // La page de connexion possède sa propre composition plein écran et ne doit
  // surtout pas déclencher le chargement du dataset avant authentification.
  if (pathname === '/login') return <>{children}</>

  return (
    <DatasetProvider>
      <AppFrame sidebarOpen={sidebarOpen} setSidebarOpen={setSidebarOpen}>{children}</AppFrame>
    </DatasetProvider>
  )
}

function AppFrame({
  children,
  sidebarOpen,
  setSidebarOpen,
}: {
  children: React.ReactNode
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
}) {
  const {
    revision,
    error,
    uploadError,
    overview,
    uploading,
    sheetSelection,
    selectSheet,
    cancelSheetSelection,
    clearError,
  } = useDataset()
  // The dialog owns the live error region while a workbook choice is pending;
  // rendering the banner too would announce the same failure twice.
  const visibleError = sheetSelection ? null : uploadError ?? (overview ? error : null)
  const recoveryWarning = overview?.dataset_recovery?.status === 'fallback'
    ? overview.dataset_recovery.message ??
      'Le dernier dataset importé n’a pas pu être restauré. Le dataset de démonstration est affiché.'
    : null
  const datasetKey = overview?.dataset.id === undefined
    ? `revision:${revision}`
    : `dataset:${overview.dataset.id}`
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        {sheetSelection ? (
          <SheetSelectionDialog
            key={`${sheetSelection.fileName}:${sheetSelection.sheets.join('\u0000')}`}
            selection={sheetSelection}
            uploading={uploading}
            error={uploadError}
            onConfirm={selectSheet}
            onCancel={cancelSheetSelection}
          />
        ) : null}
        {visibleError ? (
          <div role="alert" aria-live="assertive" className="flex items-center justify-between gap-3 border-b border-destructive/20 bg-destructive/5 px-4 py-2.5 text-xs text-destructive lg:px-6">
            <span>
              <strong className="font-semibold">{uploadError ? 'Import impossible. ' : ''}</strong>
              {visibleError}
            </span>
            <button type="button" className="font-medium underline-offset-2 hover:underline" onClick={clearError}>Fermer</button>
          </div>
        ) : null}
        {recoveryWarning ? (
          <div
            role="alert"
            data-testid="dataset-recovery-warning"
            className="flex items-start gap-2 border-b border-warning/25 bg-warning/10 px-4 py-3 text-xs text-foreground lg:px-6"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
            <span>
              <strong className="font-semibold">Reprise incomplète. </strong>
              {recoveryWarning}
            </span>
          </div>
        ) : null}
        <main key={datasetKey} className="flex-1 px-4 py-6 lg:px-6 lg:py-8">{children}</main>
      </div>
    </div>
  )
}
