'use client'

import { useCallback, useEffect, useState } from 'react'

export function useApiResource<T>(
  loader: () => Promise<T>,
  options: { enabled: boolean; revision?: number },
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!options.enabled) return
    setLoading(true)
    setError(null)
    try {
      setData(await loader())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Une erreur inattendue est survenue.')
    } finally {
      setLoading(false)
    }
  }, [loader, options.enabled])

  useEffect(() => {
    queueMicrotask(() => void load())
  }, [load, options.revision])

  return { data, loading, error, reload: load, setData }
}
