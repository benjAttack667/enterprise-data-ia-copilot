'use client'

import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'
import { DatasetProvider, useDataset } from '@/components/dataset-provider'

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
  const { revision, error, uploadError, overview, clearError } = useDataset()
  const visibleError = uploadError ?? (overview ? error : null)
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        {visibleError ? (
          <div role="alert" aria-live="assertive" className="flex items-center justify-between gap-3 border-b border-destructive/20 bg-destructive/5 px-4 py-2.5 text-xs text-destructive lg:px-6">
            <span>
              <strong className="font-semibold">{uploadError ? 'Import impossible. ' : ''}</strong>
              {visibleError}
            </span>
            <button type="button" className="font-medium underline-offset-2 hover:underline" onClick={clearError}>Fermer</button>
          </div>
        ) : null}
        <main key={revision} className="flex-1 px-4 py-6 lg:px-6 lg:py-8">{children}</main>
      </div>
    </div>
  )
}
