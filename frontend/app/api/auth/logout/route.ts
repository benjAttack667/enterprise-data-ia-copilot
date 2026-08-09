import { NextResponse, type NextRequest } from 'next/server'
import { SESSION_COOKIE_NAME, sessionCookieOptions } from '@/lib/session'

function isSameOrigin(request: NextRequest) {
  const origin = request.headers.get('origin')
  if (!origin) return true

  try {
    const originUrl = new URL(origin)
    const forwardedHost = request.headers.get('x-forwarded-host')?.split(',')[0]?.trim()
    const requestHost = forwardedHost || request.headers.get('host')
    const forwardedProtocol = request.headers.get('x-forwarded-proto')?.split(',')[0]?.trim()
    const requestProtocol = forwardedProtocol || request.nextUrl.protocol.replace(':', '')
    return originUrl.host === requestHost && originUrl.protocol === `${requestProtocol}:`
  } catch {
    return false
  }
}

export function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json(
      { error: 'Origine non autorisée.' },
      { status: 403, headers: { 'Cache-Control': 'no-store' } },
    )
  }

  const response = new NextResponse(null, {
    status: 204,
    headers: { 'Cache-Control': 'no-store' },
  })
  response.cookies.set(SESSION_COOKIE_NAME, '', {
    ...sessionCookieOptions(),
    maxAge: 0,
  })
  return response
}
