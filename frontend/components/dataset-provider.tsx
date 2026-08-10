'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError, type OverviewResponse } from '@/lib/data'
import {
  formatUploadSizeLabel,
  isSupportedDatasetFile,
  MAX_UPLOAD_SIZE_BYTES,
  SUPPORTED_UPLOAD_FORMATS_LABEL,
} from '@/lib/upload-constraints'

type DatasetContextValue = {
  overview: OverviewResponse | null
  loading: boolean
  uploading: boolean
  error: string | null
  uploadError: string | null
  uploadMaxBytes: number
  uploadMaxLabel: string
  revision: number
  refresh: () => Promise<void>
  upload: (file: File) => Promise<void>
  clearError: () => void
}

const DatasetContext = createContext<DatasetContextValue | null>(null)

function formatRetryDelay(seconds?: number) {
  if (seconds === undefined) return 'dans quelques minutes'
  if (seconds < 60) return `dans ${Math.max(1, seconds)} seconde${seconds > 1 ? 's' : ''}`
  const minutes = Math.ceil(seconds / 60)
  return `dans environ ${minutes} minute${minutes > 1 ? 's' : ''}`
}

function uploadErrorMessage(cause: unknown, uploadMaxLabel: string) {
  if (cause instanceof ApiError) {
    if (cause.status === 413) {
      return `Fichier refusé : la limite d’import est de ${uploadMaxLabel}. Choisissez un fichier plus léger.`
    }
    if (cause.status === 429) {
      return `Quota d’import temporairement atteint. Réessayez ${formatRetryDelay(cause.retryAfterSeconds)}.`
    }
    if (cause.status === 507) {
      return "Quota de stockage atteint. Aucun fichier n’a été importé ; réessayez après libération de l’espace."
    }
  }
  return cause instanceof Error ? cause.message : "L’import a échoué."
}

export function DatasetProvider({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const configuredUploadMaxBytes = overview?.storage?.uploads.max_file_bytes
  const uploadMaxBytes =
    Number.isSafeInteger(configuredUploadMaxBytes) && (configuredUploadMaxBytes ?? 0) > 0
      ? Math.min(configuredUploadMaxBytes as number, MAX_UPLOAD_SIZE_BYTES)
      : MAX_UPLOAD_SIZE_BYTES
  const uploadMaxLabel = formatUploadSizeLabel(uploadMaxBytes)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const nextOverview = await api.overview()
      setOverview(nextOverview)
      setError(null)
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
      if (!isSupportedDatasetFile(file.name)) {
        const message = `Format non pris en charge. Sélectionnez un fichier ${SUPPORTED_UPLOAD_FORMATS_LABEL}.`
        setUploadError(message)
        throw new Error(message)
      }
      if (file.size === 0) {
        const message = 'Le fichier sélectionné est vide. Choisissez un fichier contenant des données.'
        setUploadError(message)
        throw new Error(message)
      }
      if (file.size > uploadMaxBytes) {
        const message = `Le fichier dépasse la limite de ${uploadMaxLabel}. Choisissez un fichier plus léger.`
        setUploadError(message)
        throw new Error(message)
      }

      setUploading(true)
      setError(null)
      setUploadError(null)
      try {
        await api.upload(file)
        await refresh()
      } catch (cause) {
        setUploadError(uploadErrorMessage(cause, uploadMaxLabel))
        throw cause
      } finally {
        setUploading(false)
      }
    },
    [refresh, uploadMaxBytes, uploadMaxLabel],
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
      uploadError,
      uploadMaxBytes,
      uploadMaxLabel,
      revision,
      refresh,
      upload,
      clearError: () => {
        setError(null)
        setUploadError(null)
      },
    }),
    [
      error,
      loading,
      overview,
      refresh,
      revision,
      upload,
      uploadError,
      uploadMaxBytes,
      uploadMaxLabel,
      uploading,
    ],
  )

  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
}

export function useDataset() {
  const context = useContext(DatasetContext)
  if (!context) throw new Error('useDataset must be used inside DatasetProvider')
  return context
}
