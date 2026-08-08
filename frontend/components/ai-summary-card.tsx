import { Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function AiSummaryCard({ summary, mode }: { summary: string; mode?: string }) {
  return (
    <Card className="gap-0 bg-gradient-to-br from-accent to-card">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-4">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="size-4" />
          </span>
          Synthèse exécutive
        </CardTitle>
        <Badge variant="secondary" className="text-xs font-normal text-muted-foreground">
          {mode ?? 'Analyse Pandas'}
        </Badge>
      </CardHeader>
      <CardContent className="pt-4">
        <p className="text-sm leading-relaxed text-foreground text-pretty">{summary}</p>
      </CardContent>
    </Card>
  )
}
