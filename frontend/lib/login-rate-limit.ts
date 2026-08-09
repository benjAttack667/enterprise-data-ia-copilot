type LoginAttempt = {
  failures: number
  windowStartedAt: number
}

const WINDOW_MS = 15 * 60 * 1_000
const MAX_FAILURES = 5

const globalRateLimit = globalThis as typeof globalThis & {
  copilotLoginAttempts?: Map<string, LoginAttempt>
}

const attempts = globalRateLimit.copilotLoginAttempts ?? new Map<string, LoginAttempt>()
globalRateLimit.copilotLoginAttempts = attempts

function activeAttempt(identifier: string, now: number) {
  const attempt = attempts.get(identifier)
  if (attempt && now - attempt.windowStartedAt >= WINDOW_MS) {
    attempts.delete(identifier)
    return undefined
  }
  return attempt
}

export function checkLoginRateLimit(identifier: string, now = Date.now()) {
  const attempt = activeAttempt(identifier, now)
  if (!attempt || attempt.failures < MAX_FAILURES) {
    return { allowed: true, retryAfterSeconds: 0 }
  }

  return {
    allowed: false,
    retryAfterSeconds: Math.max(1, Math.ceil((attempt.windowStartedAt + WINDOW_MS - now) / 1_000)),
  }
}

export function recordLoginFailure(identifier: string, now = Date.now()) {
  const attempt = activeAttempt(identifier, now)
  if (attempt) {
    attempt.failures += 1
  } else {
    attempts.set(identifier, { failures: 1, windowStartedAt: now })
  }
}

export function clearLoginFailures(identifier: string) {
  attempts.delete(identifier)
}
