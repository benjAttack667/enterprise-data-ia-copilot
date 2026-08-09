import { createHmac, randomUUID, timingSafeEqual } from 'node:crypto'

export const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === 'production' ? '__Host-copilot_session' : 'copilot_session'
export const SESSION_TTL_SECONDS = 8 * 60 * 60

export type SessionPayload = {
  sub: 'demo'
  role: 'analyst'
  iat: number
  exp: number
  nonce: string
}

export class SessionConfigurationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SessionConfigurationError'
  }
}

function getSessionSecret() {
  const secret = process.env.SESSION_SECRET
  if (!secret || Buffer.byteLength(secret, 'utf8') < 32) {
    throw new SessionConfigurationError('SESSION_SECRET doit contenir au moins 32 octets.')
  }
  return secret
}

function sign(encodedPayload: string) {
  return createHmac('sha256', getSessionSecret()).update(encodedPayload).digest()
}

/** Crée un jeton de session signé. Le jeton ne contient aucune donnée sensible. */
export function createSessionToken(now = Date.now()) {
  const issuedAt = Math.floor(now / 1000)
  const payload: SessionPayload = {
    sub: 'demo',
    role: 'analyst',
    iat: issuedAt,
    exp: issuedAt + SESSION_TTL_SECONDS,
    nonce: randomUUID(),
  }
  const encodedPayload = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64url')
  return `${encodedPayload}.${sign(encodedPayload).toString('base64url')}`
}

/**
 * Vérifie la signature et l'expiration sans faire confiance au contenu du cookie.
 * Toute erreur de format ou de configuration produit une session invalide (fail closed).
 */
export function verifySessionToken(token: string | undefined, now = Date.now()): SessionPayload | null {
  if (!token || token.length > 2_048) return null

  try {
    const [encodedPayload, encodedSignature, extraPart] = token.split('.')
    if (!encodedPayload || !encodedSignature || extraPart !== undefined) return null

    const receivedSignature = Buffer.from(encodedSignature, 'base64url')
    const expectedSignature = sign(encodedPayload)
    if (
      receivedSignature.length !== expectedSignature.length ||
      !timingSafeEqual(receivedSignature, expectedSignature)
    ) {
      return null
    }

    const candidate = JSON.parse(Buffer.from(encodedPayload, 'base64url').toString('utf8')) as Partial<SessionPayload>
    const currentTime = Math.floor(now / 1000)
    const validLifetime =
      Number.isInteger(candidate.iat) &&
      Number.isInteger(candidate.exp) &&
      (candidate.exp as number) > (candidate.iat as number) &&
      (candidate.exp as number) - (candidate.iat as number) <= SESSION_TTL_SECONDS

    if (
      candidate.sub !== 'demo' ||
      candidate.role !== 'analyst' ||
      typeof candidate.nonce !== 'string' ||
      candidate.nonce.length < 16 ||
      !validLifetime ||
      (candidate.iat as number) > currentTime + 60 ||
      (candidate.exp as number) <= currentTime
    ) {
      return null
    }

    return candidate as SessionPayload
  } catch {
    return null
  }
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict' as const,
    path: '/',
    maxAge: SESSION_TTL_SECONDS,
  }
}
