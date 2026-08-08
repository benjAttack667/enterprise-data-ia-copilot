'use client'

import { useState } from 'react'
import { Download, FileCode2, FileText, LoaderCircle } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api, type ReportFormat, type ReportResponse } from '@/lib/data'

function downloadReport(report: ReportResponse) {
  const mime = report.format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8'
  const url = URL.createObjectURL(new Blob([report.content], { type: mime }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = report.filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export default function ReportsPage() {
  const datasetState = useDataset()
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [generating, setGenerating] = useState<ReportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function generate(format: ReportFormat) {
    setGenerating(format)
    setError(null)
    try {
      setReport(await api.report(format))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'La génération du rapport a échoué.')
    } finally {
      setGenerating(null)
    }
  }

  if (datasetState.loading && !datasetState.overview) return <LoadingState />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (!datasetState.overview) return <EmptyDatasetState />

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Rapports" description="Rapport généré côté backend à partir de l’analyse courante">
        <Button variant="outline" size="sm" className="gap-1.5" disabled={Boolean(generating)} onClick={() => void generate('markdown')}>
          {generating === 'markdown' ? <LoaderCircle className="size-4 animate-spin" /> : <FileText className="size-4" />} Markdown
        </Button>
        <Button size="sm" className="gap-1.5" disabled={Boolean(generating)} onClick={() => void generate('html')}>
          {generating === 'html' ? <LoaderCircle className="size-4 animate-spin" /> : <FileCode2 className="size-4" />} HTML
        </Button>
      </PageHeader>

      {error ? <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}

      {report ? (
        <Card className="gap-0 overflow-hidden py-0">
          <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div>
              <CardTitle className="text-sm font-semibold">{report.filename}</CardTitle>
              <CardDescription className="mt-1 text-xs">Format {report.format.toUpperCase()} · contenu produit par FastAPI</CardDescription>
            </div>
            <Button type="button" size="sm" className="gap-1.5" onClick={() => downloadReport(report)}>
              <Download className="size-4" /> Télécharger
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            <pre data-testid="report-content" className="max-h-[640px] overflow-auto whitespace-pre-wrap break-words bg-slate-950 p-6 font-mono text-xs leading-relaxed text-slate-100">{report.content}</pre>
          </CardContent>
        </Card>
      ) : (
        <Card className="flex min-h-80 items-center justify-center border-dashed p-8">
          <div className="max-w-md text-center">
            <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary"><FileText className="size-6" /></span>
            <p className="mt-4 text-sm font-semibold text-foreground">Générer le rapport d’analyse</p>
            <p className="mt-1 text-sm text-muted-foreground">Choisissez Markdown ou HTML. Le contenu pourra ensuite être prévisualisé et téléchargé.</p>
          </div>
        </Card>
      )}
    </div>
  )
}
