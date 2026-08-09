import { createHash, timingSafeEqual } from 'node:crypto'
import { NextResponse, type NextRequest } from 'next/server'
import {
  createSessionToken,
  SESSION_COOKIE_NAME,
  SessionConfigurationError,
  sessionCookieOptions,
} from '@/lib/session'
import {
  checkLoginRateLimit,
  clearLoginFailures,
  recordLoginFailure,
} from '@/lib/login-rate-limit'

const MAX_REQUEST_BYTES = 1_024
const FAILURE_DELAY_MS = 300

function clientIdentifier(request: NextRequest) {
  const realIp = request.headers.get('x-real-ip')
  const forwardedIp = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim()
  return realIp || forwardedIp || 'unknown-client'
}

function constantTimeMatch(candidate: string, expected: string) {
  const candidateDigest = createHash('sha256').update(candidate, 'utf8').digest()
  const expectedDigest = createHash('sha256').update(expected, 'utf8').digest()
  return timingSafeEqual(candidateDigest, expectedDigest)
}

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

function errorResponse(message: string, status: number, headers?: HeadersInit) {
  return NextResponse.json(
    { error: message },
    {
      status,
      headers: { 'Cache-Control': 'no-store', ...headers },
    },
  )
}

async function readLimitedBody(request: NextRequest) {
  if (!request.body) return { text: '', tooLarge: false }

  const reader = request.body.getReader()
  const decoder = new TextDecoder()
  let totalBytes = 0
  let text = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    totalBytes += value.byteLength
    if (totalBytes > MAX_REQUEST_BYTES) {
      await reader.cancel().catch(() => undefined)
      return { text: '', tooLarge: true }
    }
    text += decoder.decode(value, { stream: true })
  }

  text += decoder.decode()
  return { text, tooLarge: false }
}

export async function POST(request: NextRequest) {
  const identifier = clientIdentifier(request)
  const rateLimit = checkLoginRateLimit(identifier)
  if (!rateLimit.allowed) {
    return errorResponse('Trop de tentatives. Réessayez dans quelques minutes.', 429, {
      'Retry-After': String(rateLimit.retryAfterSeconds),
    })
  }

  const contentLength = Number(request.headers.get('content-length') ?? 0)
  if (contentLength > MAX_REQUEST_BYTES) {
    return errorResponse('Requête invalide.', 413)
  }
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse('Requête invalide.', 415)
  }

  let password = ''
  try {
    const payload = await readLimitedBody(request)
    if (payload.tooLarge) return errorResponse('Requête invalide.', 413)
    const body = JSON.parse(payload.text) as { password?: unknown }
    if (typeof body.password === 'string' && body.password.length <= 256) {
      password = body.password
    }
  } catch {
    return errorResponse('Requête invalide.', 400)
  }

  const expectedPassword = process.env.DEMO_ACCESS_PASSWORD
  if (!expectedPassword || expectedPassword.length < 12) {
    console.error('[auth] DEMO_ACCESS_PASSWORD est absent ou trop court.')
    return errorResponse('Le service de connexion est temporairement indisponible.', 503)
  }

  if (!password || !constantTimeMatch(password, expectedPassword)) {
    recordLoginFailure(identifier)
    await wait(FAILURE_DELAY_MS)
    return errorResponse('Mot de passe incorrect.', 401)
  }

  try {
    const response = NextResponse.json(
      { authenticated: true },
      { headers: { 'Cache-Control': 'no-store' } },
    )
    response.cookies.set(SESSION_COOKIE_NAME, createSessionToken(), sessionCookieOptions())
    clearLoginFailures(identifier)
    return response
  } catch (error) {
    if (error instanceof SessionConfigurationError) {
      console.error(`[auth] ${error.message}`)
      return errorResponse('Le service de connexion est temporairement indisponible.', 503)
    }
    throw error
  }
}
