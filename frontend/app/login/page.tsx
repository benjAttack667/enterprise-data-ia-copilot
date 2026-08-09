import type { Metadata } from 'next'
import { BarChart3, Database, LockKeyhole, Radar, ShieldCheck, Sparkles } from 'lucide-react'
import { LoginForm } from '@/components/login-form'

export const metadata: Metadata = {
  title: 'Connexion | Enterprise Data & IA Copilot',
  description: 'Accès sécurisé au workspace Enterprise Data & IA Copilot.',
}

function safeDestination(value: string | string[] | undefined) {
  const destination = Array.isArray(value) ? value[0] : value
  if (
    !destination ||
    !destination.startsWith('/') ||
    destination.startsWith('//') ||
    destination.startsWith('/login') ||
    destination.startsWith('/api/')
  ) {
    return '/'
  }
  return destination
}

const capabilities = [
  { icon: ShieldCheck, label: 'Audit de qualité des données' },
  { icon: BarChart3, label: 'Dashboards et KPI automatiques' },
  { icon: Radar, label: 'Détection d’anomalies ML' },
  { icon: Sparkles, label: 'Assistant IA avec fallback local' },
]

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>
}) {
  const params = await searchParams

  return (
    <main className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(37,99,235,0.25),transparent_35%),radial-gradient(circle_at_85%_80%,rgba(14,165,233,0.14),transparent_35%)]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,.15)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.15)_1px,transparent_1px)] [background-size:32px_32px]"
      />

      <div className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-12 px-5 py-10 lg:grid-cols-[1.05fr_0.95fr] lg:px-10">
        <section className="mx-auto max-w-2xl lg:mx-0">
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-600/20">
              <Database className="size-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-base font-semibold">Enterprise Data &amp; IA</p>
              <p className="text-sm text-slate-400">Copilot Platform</p>
            </div>
          </div>

          <div className="mt-12 max-w-xl">
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-300">
              Workspace analytique sécurisé
            </p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
              Transformez vos données en décisions actionnables.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-slate-300 sm:text-lg">
              Une plateforme unifiée pour auditer, explorer et expliquer vos données avec Python,
              le machine learning et l’IA générative.
            </p>
          </div>

          <ul className="mt-9 grid max-w-xl gap-3 sm:grid-cols-2">
            {capabilities.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-3 text-sm text-slate-300">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/5 ring-1 ring-white/10">
                  <Icon className="size-4 text-blue-300" aria-hidden="true" />
                </span>
                {label}
              </li>
            ))}
          </ul>
        </section>

        <section className="mx-auto w-full max-w-md" aria-labelledby="login-title">
          <div className="rounded-2xl border border-white/10 bg-white/[0.97] p-6 text-slate-950 shadow-2xl shadow-black/30 backdrop-blur sm:p-8">
            <div className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700 ring-1 ring-blue-100">
              <LockKeyhole className="size-5" aria-hidden="true" />
            </div>
            <h2 id="login-title" className="mt-5 text-2xl font-semibold tracking-tight">
              Connexion au workspace
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Cet environnement de démonstration est privé. Authentifiez-vous pour accéder aux
              analyses et aux données.
            </p>

            <LoginForm destination={safeDestination(params.next)} />

            <div className="mt-6 border-t border-slate-200 pt-5">
              <div className="flex items-start gap-2.5 text-xs leading-relaxed text-slate-500">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                <p>
                  Session protégée par un cookie HttpOnly signé. Les secrets du backend ne sont
                  jamais exposés au navigateur.
                </p>
              </div>
            </div>
          </div>
          <p className="mt-5 text-center text-xs text-slate-500">
            Données de démonstration uniquement · Accès contrôlé
          </p>
        </section>
      </div>
    </main>
  )
}
