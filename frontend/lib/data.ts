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
  value: string | number | null
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
  missing?: number | null
  missing_rate?: number | null
}

export type CategoryPoint = {
  name: string
  value: number
}

export type TrendPoint = {
  label?: string
  date?: string
  period?: string
  value?: number | null
  [key: string]: string | number | null | undefined
}

export type SeriesMetadata = {
  series_kind?: 'temporal' | 'categorical' | 'empty' | string
  missing_dimension_count?: number
  invalid_dimension_count?: number
  dimension_parse_rate?: number | null
  missing_label?: string
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
  series_kind?: 'temporal' | 'categorical' | 'empty' | string
  trend_series_kind?: SeriesMetadata['series_kind']
  trend_meta?: SeriesMetadata
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
  dtype?: string | null
  semantic_type?: string | null
  inferred_type?: string | null
  parse_rate?: number | null
  blank_count?: number | null
  missing?: number | null
  missing_count?: number | null
  missing_rate?: number | null
  unique?: number | null
  unique_count?: number | null
  invalid_count?: number | null
  invalid_numeric_count?: number | null
  duplicate_impact?: number | null
  type_consistency?: number | null
  score?: number | null
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
  series_kind?: SeriesMetadata['series_kind']
  missing_dimension_count?: number
  invalid_dimension_count?: number
  dimension_parse_rate?: number | null
  missing_label?: string
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
  total_count?: number
  returned_count?: number
  truncated?: boolean
  rate: number
  rows: Array<Record<string, unknown>>
  numeric_columns?: string[]
  excluded_identifier_columns?: string[]
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

const MAX_BUSY_RETRIES = 3
const MAX_AUTOMATIC_UPLOAD_RETRY_SECONDS = 5

function wait(milliseconds: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds))
}

async function executeRequest<T>(
  path: string,
  init: RequestInit | undefined,
  method: string,
): Promise<T> {
  let response: Response

  for (let attempt = 0; ; attempt += 1) {
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

    const seconds = retryAfterSeconds(response.headers.get('retry-after'))
    // Le backend sérialise les calculs lourds et renvoie l'upload avant même
    // de lire son corps lorsque le slot est occupé. Les GET sont toujours sûrs
    // à rejouer ; un upload ne l'est que pour une attente courte, ce qui exclut
    // le quota glissant de plusieurs minutes.
    const retryableBusyRequest =
      method === 'GET' ||
      (method === 'POST' &&
        path === '/api/upload' &&
        seconds !== undefined &&
        seconds <= MAX_AUTOMATIC_UPLOAD_RETRY_SECONDS)
    if (
      response.status === 429 &&
      retryableBusyRequest &&
      attempt < MAX_BUSY_RETRIES
    ) {
      if (response.body) await response.body.cancel().catch(() => undefined)
      await wait(Math.min(Math.max(seconds ?? 1, 1), 5) * 1_000)
      continue
    }
    break
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase()
  return executeRequest<T>(path, init, method)
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
