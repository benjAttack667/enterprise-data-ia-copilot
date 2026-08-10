import { NextResponse, type NextRequest } from 'next/server'
import { SESSION_COOKIE_NAME, verifySessionToken } from '@/lib/session'
import { MAX_UPLOAD_REQUEST_BYTES, MAX_UPLOAD_SIZE_LABEL } from '@/lib/upload-constraints'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type ProxyContext = {
  params: Promise<{ path: string[] }>
}

type RequestInitWithDuplex = RequestInit & { duplex?: 'half' }

const ALLOWED_BACKEND_ROUTES = new Map<string, ReadonlySet<string>>([
  ['/api/upload', new Set(['POST'])],
  ['/api/overview', new Set(['GET'])],
  ['/api/data-quality', new Set(['GET'])],
  ['/api/dashboard', new Set(['GET'])],
  ['/api/ai-summary', new Set(['POST'])],
  ['/api/ask', new Set(['POST'])],
  ['/api/anomalies', new Set(['GET'])],
  ['/api/report', new Set(['POST'])],
  ['/api/history', new Set(['GET'])],
])

function configuration() {
  const backendUrl = process.env.BACKEND_INTERNAL_URL
  const serviceToken = process.env.BACKEND_SERVICE_TOKEN

  if (!backendUrl || !serviceToken || Buffer.byteLength(serviceToken, 'utf8') < 32) return null

  try {
    const baseUrl = new URL(backendUrl.endsWith('/') ? backendUrl : `${backendUrl}/`)
    if (!['http:', 'https:'].includes(baseUrl.protocol)) return null
    return { baseUrl, serviceToken }
  } catch {
    return null
  }
}

function jsonError(message: string, status: number) {
  return NextResponse.json(
    { detail: message },
    { status, headers: { 'Cache-Control': 'no-store' } },
  )
}

async function forward(request: NextRequest, context: ProxyContext) {
  const session = verifySessionToken(request.cookies.get(SESSION_COOKIE_NAME)?.value)
  if (!session) return jsonError('Session absente ou expirée.', 401)

  const config = configuration()
  if (!config) {
    console.error('[proxy] BACKEND_INTERNAL_URL ou BACKEND_SERVICE_TOKEN est invalide.')
    return jsonError("Le service d'analyse est temporairement indisponible.", 503)
  }

  const { path } = await context.params
  const backendPath = `/${path.join('/')}`
  const allowedMethods = ALLOWED_BACKEND_ROUTES.get(backendPath)
  if (!allowedMethods) return jsonError('Ressource introuvable.', 404)
  if (!allowedMethods.has(request.method)) return jsonError('Méthode non autorisée.', 405)

  if (backendPath === '/api/upload') {
    const contentLengthHeader = request.headers.get('content-length')
    if (contentLengthHeader !== null) {
      // Content-Length est un entier décimal HTTP. Éviter Number() empêche
      // d'accepter silencieusement des syntaxes comme 1e9 ou 0x100.
      if (!/^\d+$/.test(contentLengthHeader)) {
        return jsonError('Taille de requête invalide.', 400)
      }
      if (BigInt(contentLengthHeader) > BigInt(MAX_UPLOAD_REQUEST_BYTES)) {
        return jsonError(
          `Fichier refusé : la limite d’import est de ${MAX_UPLOAD_SIZE_LABEL}.`,
          413,
        )
      }
    }
    // Garde précoce uniquement : une requête HTTP en transfert segmenté peut
    // omettre Content-Length. FastAPI doit donc conserver sa limite de flux,
    // qui reste l'autorité sans que le BFF ne bufferise le multipart.
  }

  // La liste blanche empêche tout path traversal et évite d'exposer
  // automatiquement de futurs endpoints FastAPI au navigateur.
  const targetUrl = new URL(backendPath, config.baseUrl)
  targetUrl.search = request.nextUrl.search

  const headers = new Headers({
    Accept: request.headers.get('accept') ?? 'application/json',
    Authorization: `Bearer ${config.serviceToken}`,
  })
  const contentType = request.headers.get('content-type')
  if (contentType) headers.set('Content-Type', contentType)

  const init: RequestInitWithDuplex = {
    method: request.method,
    headers,
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(90_000),
  }
  if (request.method !== 'GET' && request.method !== 'HEAD' && request.body) {
    init.body = request.body
    init.duplex = 'half'
  }

  try {
    const upstream = await fetch(targetUrl, init)
    const responseHeaders = new Headers({
      'Cache-Control': 'no-store',
    })
    for (const name of ['content-type', 'content-disposition', 'retry-after', 'x-request-id']) {
      const value = upstream.headers.get(name)
      if (value) responseHeaders.set(name, value)
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    if (error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
      return jsonError("Le service d'analyse a dépassé le délai autorisé.", 504)
    }
    console.error('[proxy] Le backend FastAPI est injoignable.')
    return jsonError("Le service d'analyse est temporairement indisponible.", 502)
  }
}

export const GET = forward
export const POST = forward
