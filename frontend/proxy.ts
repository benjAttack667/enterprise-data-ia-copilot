import { NextResponse, type NextRequest } from 'next/server'
import { SESSION_COOKIE_NAME, verifySessionToken } from '@/lib/session'

function safeDestination(pathname: string, search: string) {
  const destination = `${pathname}${search}`
  if (!destination.startsWith('/') || destination.startsWith('//') || destination.startsWith('/login')) {
    return '/'
  }
  return destination
}

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  const isAuthenticated = Boolean(
    verifySessionToken(request.cookies.get(SESSION_COOKIE_NAME)?.value),
  )

  if (pathname.startsWith('/api/auth/')) return NextResponse.next()

  if (pathname === '/login') {
    return isAuthenticated
      ? NextResponse.redirect(new URL('/', request.url))
      : NextResponse.next()
  }

  if (isAuthenticated) return NextResponse.next()

  if (pathname.startsWith('/api/copilot/')) {
    return NextResponse.json(
      { detail: 'Session absente ou expirée.' },
      { status: 401, headers: { 'Cache-Control': 'no-store' } },
    )
  }

  const loginUrl = new URL('/login', request.url)
  if (request.method === 'GET' || request.method === 'HEAD') {
    loginUrl.searchParams.set('next', safeDestination(pathname, request.nextUrl.search))
  }
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|apple-icon.png|icon.svg|icon-light-32x32.png|icon-dark-32x32.png).*)',
  ],
}
