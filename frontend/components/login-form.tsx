'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowRight, LoaderCircle, LockKeyhole } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function LoginForm({ destination }: { destination: string }) {
  const router = useRouter()
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })

      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: string } | null
        setError(body?.error ?? 'Connexion impossible. Réessayez.')
        return
      }

      router.replace(destination)
      router.refresh()
    } catch {
      setError('Connexion impossible. Vérifiez votre réseau puis réessayez.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-7 space-y-5">
      <div className="space-y-2">
        <label htmlFor="password" className="text-sm font-medium text-foreground">
          Mot de passe d’accès
        </label>
        <div className="relative">
          <LockKeyhole
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            autoFocus
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'login-error' : 'login-help'}
            placeholder="Saisissez le mot de passe"
            className="h-11 pl-10 pr-3"
          />
        </div>
        <p id="login-help" className="text-xs leading-relaxed text-muted-foreground">
          Utilisez le mot de passe communiqué par le propriétaire de la démonstration.
        </p>
      </div>

      {error ? (
        <div
          id="login-error"
          role="alert"
          className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <Button type="submit" size="lg" className="h-11 w-full" disabled={submitting || !password}>
        {submitting ? (
          <>
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            Connexion…
          </>
        ) : (
          <>
            Accéder au workspace
            <ArrowRight className="size-4" aria-hidden="true" />
          </>
        )}
      </Button>
    </form>
  )
}
