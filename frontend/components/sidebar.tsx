'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  ShieldCheck,
  BarChart3,
  Sparkles,
  Radar,
  FileText,
  History,
  Database,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const nav = [
  { label: 'Vue d’ensemble', href: '/', icon: LayoutDashboard },
  { label: 'Qualité des données', href: '/data-quality', icon: ShieldCheck },
  { label: 'Tableau de bord', href: '/dashboard', icon: BarChart3 },
  { label: 'Assistant IA', href: '/ai-assistant', icon: Sparkles },
  { label: 'Anomalies', href: '/anomalies', icon: Radar },
  { label: 'Rapports', href: '/reports', icon: FileText },
  { label: 'Historique', href: '/history', icon: History },
]

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname()

  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-foreground/40 lg:hidden"
          onClick={onClose}
          aria-hidden
        />
      ) : null}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-200 lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center justify-between gap-2 border-b border-sidebar-border px-5">
          <Link href="/" className="flex items-center gap-2.5" onClick={onClose}>
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Database className="size-4" />
            </span>
            <span className="text-sm font-semibold leading-tight text-sidebar-foreground">
              Data & IA
              <span className="block text-xs font-normal text-muted-foreground">Copilot</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-sidebar-accent lg:hidden"
            aria-label="Fermer la navigation"
          >
            <X className="size-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          <p className="px-3 pb-2 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Espace de travail
          </p>
          {nav.map((item) => {
            const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/60',
                )}
              >
                <Icon className={cn('size-4 shrink-0', active ? 'text-primary' : 'text-muted-foreground')} />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="border-t border-sidebar-border p-3">
          <div className="rounded-lg bg-accent p-3">
            <p className="text-xs font-medium text-accent-foreground">Moteur d’analyse</p>
            <p className="mt-1 text-xs text-muted-foreground">FastAPI · Pandas · scikit-learn</p>
          </div>
        </div>
      </aside>
    </>
  )
}
