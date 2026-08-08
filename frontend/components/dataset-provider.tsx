'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError, type OverviewResponse } from '@/lib/data'

type DatasetContextValue = {
  overview: OverviewResponse | null
  loading: boolean
  uploading: boolean
  error: string | null
  revision: number
  refresh: () => Promise<void>
  upload: (file: File) => Promise<void>
  clearError: () => void
}

const DatasetContext = createContext<DatasetContextValue | null>(null)
const MAX_FILE_SIZE = 50 * 1024 * 1024
const SUPPORTED_EXTENSIONS = ['csv', 'xlsx']

export function DatasetProvider({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setOverview(await api.overview())
      setRevision((value) => value + 1)
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 404 || cause.status === 409)) {
        setOverview(null)
      } else {
        setError(cause instanceof Error ? cause.message : 'Impossible de charger le dataset actif.')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const upload = useCallback(
    async (file: File) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
      if (!SUPPORTED_EXTENSIONS.includes(extension)) {
        const message = 'Format non pris en charge. Utilisez un fichier CSV ou XLSX.'
        setError(message)
        throw new Error(message)
      }
      if (file.size > MAX_FILE_SIZE) {
        const message = 'Le fichier dépasse la limite de 50 Mio.'
        setError(message)
        throw new Error(message)
      }

      setUploading(true)
      setError(null)
      try {
        await api.upload(file)
        await refresh()
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "L'import a échoué."
        setError(message)
        throw cause
      } finally {
        setUploading(false)
      }
    },
    [refresh],
  )

  useEffect(() => {
    queueMicrotask(() => void refresh())
  }, [refresh])

  const value = useMemo(
    () => ({
      overview,
      loading,
      uploading,
      error,
      revision,
      refresh,
      upload,
      clearError: () => setError(null),
    }),
    [error, loading, overview, refresh, revision, upload, uploading],
  )

  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
}

export function useDataset() {
  const context = useContext(DatasetContext)
  if (!context) throw new Error('useDataset must be used inside DatasetProvider')
  return context
}
