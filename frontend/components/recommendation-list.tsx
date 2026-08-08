import { ArrowRight, Lightbulb } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SeverityBadge } from '@/components/severity-badge'
import type { Recommendation } from '@/lib/data'

export function RecommendationList({ recommendations }: { recommendations: Array<Recommendation | string> }) {
  return (
    <Card className="gap-0">
      <CardHeader className="flex flex-row items-center gap-2 border-b border-border pb-4">
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Lightbulb className="size-4" />
        </span>
        <CardTitle className="text-sm font-semibold">Recommandations</CardTitle>
      </CardHeader>
      <CardContent className="pt-2">
        {recommendations.length ? (
          <ul className="divide-y divide-border">
            {recommendations.map((item, index) => {
              const recommendation = typeof item === 'string' ? { title: item } : item
              return (
                <li key={recommendation.id ?? `${recommendation.title}-${index}`} className="flex items-start gap-3 py-3">
                  <ArrowRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-foreground">{recommendation.title}</p>
                      {recommendation.severity ? <SeverityBadge severity={recommendation.severity} /> : null}
                    </div>
                    {recommendation.detail ? (
                      <p className="mt-0.5 text-xs text-muted-foreground text-pretty">{recommendation.detail}</p>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="py-5 text-sm text-muted-foreground">Aucune action prioritaire détectée.</p>
        )}
      </CardContent>
    </Card>
  )
}
