'use client'

import { PageHeader } from '@/components/page-header'
import { KpiCard } from '@/components/kpi-card'
import { ChartCard } from '@/components/chart-card'
import { AiSummaryCard } from '@/components/ai-summary-card'
import { RecommendationList } from '@/components/recommendation-list'
import {
  QualityByColumnChart,
  MissingValuesChart,
  OverviewTrendChart,
  CategoryBreakdownChart,
} from '@/components/charts'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'

function formatUpdatedAt(value?: string) {
  if (!value) return 'analyse courante'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
}

export default function OverviewPage() {
  const { overview, loading, error, refresh } = useDataset()

  if (loading && !overview) return <LoadingState />
  if (error && !overview) return <ErrorState message={error} retry={refresh} />
  if (!overview) return <EmptyDatasetState />

  const { dataset } = overview
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Vue d’ensemble"
        description={`${dataset.name} · ${dataset.rows.toLocaleString('fr-FR')} lignes · ${formatUpdatedAt(dataset.updated_at ?? dataset.uploaded_at)}`}
      />

      <section aria-label="Indicateurs clés" className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {overview.kpis.map((kpi, index) => <KpiCard key={kpi.id ?? `${kpi.label}-${index}`} kpi={kpi} />)}
      </section>

      <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartCard title="Tendance métier" description="Série calculée automatiquement sur le dataset actif">
            <OverviewTrendChart data={overview.trend} />
          </ChartCard>
        </div>
        <ChartCard title="Répartition par catégorie" description="Principales catégories détectées">
          <CategoryBreakdownChart data={overview.category_breakdown} />
        </ChartCard>
      </section>

      <section className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Qualité par colonne" description="Score composite sur 100">
          <QualityByColumnChart data={overview.quality_by_column} />
        </ChartCard>
        <ChartCard title="Valeurs manquantes" description="Taux de valeurs nulles par colonne">
          <MissingValuesChart data={overview.missing_distribution} />
        </ChartCard>
      </section>

      <section className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AiSummaryCard summary={overview.summary} />
        <RecommendationList recommendations={overview.recommendations} />
      </section>
    </div>
  )
}
