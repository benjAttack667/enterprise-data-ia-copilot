'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { LoaderCircle, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function LogoutButton() {
  const router = useRouter()
  const [submitting, setSubmitting] = useState(false)

  async function logout() {
    setSubmitting(true)
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
    } finally {
      router.replace('/login')
      router.refresh()
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={logout}
      disabled={submitting}
      aria-label="Se déconnecter"
      title="Se déconnecter"
      className="text-muted-foreground"
    >
      {submitting ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        <LogOut className="size-4" aria-hidden="true" />
      )}
      <span className="hidden xl:inline">Déconnexion</span>
    </Button>
  )
}
