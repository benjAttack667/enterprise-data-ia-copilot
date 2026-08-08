'use client'

import { useState } from 'react'
import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'
import { DatasetProvider, useDataset } from '@/components/dataset-provider'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
  const { revision, error, overview, clearError } = useDataset()
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        {error && overview ? (
          <div role="alert" className="flex items-center justify-between gap-3 border-b border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive lg:px-6">
            <span>{error}</span>
            <button type="button" className="font-medium underline-offset-2 hover:underline" onClick={clearError}>Fermer</button>
          </div>
        ) : null}
        <main key={revision} className="flex-1 px-4 py-6 lg:px-6 lg:py-8">{children}</main>
      </div>
    </div>
  )
}
