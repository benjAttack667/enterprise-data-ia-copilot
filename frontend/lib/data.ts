/**
 * Typed HTTP client for the FastAPI backend.
 *
 * Keeping the API contract in one file makes the frontend easy to explain and
 * prevents UI components from knowing transport details.
 */

// Le navigateur ne contacte jamais FastAPI directement. Cette route same-origin
// vérifie la session puis ajoute le jeton de service côté serveur uniquement.
export const API_URL = '/api/copilot'

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type DatasetInfo = {
  id?: string | number
  name: string
  rows: number
  columns: number
  source?: string
  uploaded_at?: string
  updated_at?: string
}

export type Kpi = {
  id?: string
  label: string
  value: string | number
  unit?: string
  hint?: string
  delta?: { value: string; direction: 'up' | 'down' }
  tone?: 'default' | 'neutral' | 'success' | 'warning' | 'danger'
}

export type Recommendation = {
  id?: string | number
  title: string
  detail?: string
  severity?: Severity
}

export type QualityPoint = {
  column: string
  score: number
}

export type MissingPoint = {
  column: string
  missing?: number
  missing_rate?: number
}

export type CategoryPoint = {
  name: string
  value: number
}

export type TrendPoint = {
  label?: string
  date?: string
  period?: string
  value?: number
  [key: string]: string | number | undefined
}

export type StorageUsage = {
  uploads: {
    files: number
    bytes: number
    max_files: number
    max_file_bytes: number
  }
  reports: {
    files: number
    bytes: number
    max_files: number
  }
  history: {
    entries: number
    max_entries: number
    files: number
    bytes: number
  }
}

export type OverviewResponse = {
  dataset: DatasetInfo
  kpis: Kpi[]
  quality_score: number
  summary: string
  recommendations: Array<Recommendation | string>
  quality_by_column: QualityPoint[]
  missing_distribution: MissingPoint[]
  category_breakdown: CategoryPoint[]
  trend: TrendPoint[]
  storage?: StorageUsage
}

export type QualityProblem = {
  id?: string | number
  column?: string
  title?: string
  message?: string
  detail?: string
  severity?: Severity
}

export type ColumnQuality = {
  column: string
  dtype?: string
  missing?: number
  missing_count?: number
  missing_rate?: number
  unique?: number
  unique_count?: number
  duplicate_impact?: number
  type_consistency?: number
  score?: number
  status?: string
  issues?: string[]
  severity?: Severity
  action?: string
}

export type DataQualityResponse = {
  score: number
  summary: string | Record<string, number>
  problems: Array<QualityProblem | string>
  recommendations: Array<Recommendation | string>
  columns: ColumnQuality[]
}

export type DashboardDatum = Record<string, string | number | null>

export type DashboardResponse = {
  dimension: string
  metric: string
  aggregation: string
  dimension_options: string[]
  metric_options: string[]
  aggregation_options: string[]
  chart_type: 'bar' | 'line' | 'area' | 'pie' | string
  data: DashboardDatum[]
  kpis: Kpi[]
}

export type AiResponse = {
  summary: string
  answer?: string
  findings?: string[]
  actions?: string[]
  recommendations?: string[]
  suggestions?: string[]
  mode?: string
  model?: string
  generated_at?: string
}

export type AnomaliesResponse = {
  applicable?: boolean
  count: number
  rate: number
  rows: Array<Record<string, unknown>>
  numeric_columns?: string[]
  method?: string
  message?: string
  parameters?: Record<string, string | number | null>
}

export type ReportFormat = 'markdown' | 'html'

export type ReportResponse = {
  filename: string
  format: ReportFormat
  content: string
}

export type HistoryEntry = {
  id: string | number
  action?: string
  event_type?: string
  dataset?: string
  dataset_name?: string
  timestamp?: string
  created_at?: string
  status?: 'completed' | 'processing' | 'failed' | string
  details?: string | Record<string, unknown>
}

export type HistoryResponse = { items: HistoryEntry[] }

export type UploadResponse = {
  dataset?: DatasetInfo
  message?: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function retryAfterSeconds(value: string | null) {
  if (!value) return undefined

  const seconds = Number(value)
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds)

  const retryDate = Date.parse(value)
  if (Number.isNaN(retryDate)) return undefined
  return Math.max(0, Math.ceil((retryDate - Date.now()) / 1_000))
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError("Impossible de joindre le service d'analyse.")
  }

  if (response.status === 401 && typeof window !== 'undefined') {
    const destination = `${window.location.pathname}${window.location.search}`
    // Le client HTTP n'est pas un composant React : un remplacement complet
    // garantit aussi que les données du workspace quittent la mémoire du navigateur.
    window.location.replace(`/login?next=${encodeURIComponent(destination)}`)
    throw new ApiError('Votre session a expiré. Reconnexion en cours…', 401)
  }

  if (!response.ok) {
    let message = `Erreur API (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> }
      if (typeof body.detail === 'string') message = body.detail
      if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).filter(Boolean).join(', ') || message
      }
    } catch {
      const text = await response.text().catch(() => '')
      if (text) message = text
    }
    throw new ApiError(
      message,
      response.status,
      retryAfterSeconds(response.headers.get('retry-after')),
    )
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function queryString(params: Record<string, string | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value)
  })
  const serialized = search.toString()
  return serialized ? `?${serialized}` : ''
}

export const api = {
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return request<UploadResponse>('/api/upload', { method: 'POST', body: form })
  },

  overview() {
    return request<OverviewResponse>('/api/overview')
  },

  dataQuality() {
    return request<DataQualityResponse>('/api/data-quality')
  },

  dashboard(params: { dimension?: string; metric?: string; aggregation?: string } = {}) {
    return request<DashboardResponse>(`/api/dashboard${queryString(params)}`)
  },

  aiSummary() {
    return request<AiResponse>('/api/ai-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  },

  async ask(question: string): Promise<AiResponse> {
    const response = await request<AiResponse>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    return { ...response, summary: response.summary ?? response.answer ?? '' }
  },

  anomalies() {
    return request<AnomaliesResponse>('/api/anomalies')
  },

  report(format: ReportFormat) {
    return request<ReportResponse>('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format }),
    })
  },

  history() {
    return request<HistoryResponse>('/api/history')
  },
}
