'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Bot, LoaderCircle, Send, Sparkles, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/components/page-header'
import { EmptyDatasetState, ErrorState, LoadingState } from '@/components/async-state'
import { useDataset } from '@/components/dataset-provider'
import { api, type AiResponse } from '@/lib/data'

type Message = { role: 'user'; content: string } | { role: 'assistant'; content: AiResponse }

const questionSuggestions = [
  'Quels sont les principaux problèmes de qualité ?',
  'Quelles anomalies dois-je examiner en priorité ?',
  'Quelles actions recommandes-tu sur ce dataset ?',
]

function ModeBadge({ mode }: { mode?: string }) {
  if (!mode) return null
  return (
    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary ring-1 ring-inset ring-primary/20">
      {mode === 'openai' ? 'OpenAI' : 'Fallback local'}
    </span>
  )
}

export default function AiAssistantPage() {
  const datasetState = useDataset()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [summary, setSummary] = useState<AiResponse | null>(null)
  const [sending, setSending] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function generateSummary() {
    setGenerating(true)
    setError(null)
    try {
      setSummary(await api.aiSummary())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'La synthèse a échoué.')
    } finally {
      setGenerating(false)
    }
  }

  async function send(question: string) {
    const value = question.trim()
    if (!value || sending) return
    setMessages((previous) => [...previous, { role: 'user', content: value }])
    setInput('')
    setSending(true)
    setError(null)
    try {
      const answer = await api.ask(value)
      setMessages((previous) => [...previous, { role: 'assistant', content: answer }])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "L'assistant n'a pas pu répondre.")
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send(input)
    }
  }

  if (datasetState.loading && !datasetState.overview) return <LoadingState />
  if (datasetState.error && !datasetState.overview) return <ErrorState message={datasetState.error} retry={datasetState.refresh} />
  if (!datasetState.overview) return <EmptyDatasetState />

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Assistant IA" description="Questions et synthèses fondées sur les données réellement chargées" />

      {error ? <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}

      <Card className="mb-4 bg-gradient-to-br from-accent to-card p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
              <h3 className="text-sm font-semibold text-foreground">Synthèse du dataset actif</h3>
              <ModeBadge mode={summary?.mode} />
            </div>
            {summary ? (
              <div className="mt-3 space-y-3">
                <p className="text-sm leading-relaxed text-foreground">{summary.summary}</p>
                {summary.recommendations?.length ? (
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    {summary.recommendations.map((item, index) => <li key={index} className="flex gap-2"><ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" />{item}</li>)}
                  </ul>
                ) : null}
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">Générez une synthèse via OpenAI, avec fallback local automatique si aucune clé n’est configurée.</p>
            )}
          </div>
          <Button type="button" size="sm" className="shrink-0 gap-1.5" disabled={generating} onClick={() => void generateSummary()}>
            {generating ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {summary ? 'Régénérer' : 'Générer'}
          </Button>
        </div>
      </Card>

      <Card className="flex h-[560px] flex-col gap-0 py-0">
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {!messages.length ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <span className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary"><Bot className="size-6" /></span>
              <p className="mt-4 text-sm font-medium text-foreground">Interroger le Data Copilot</p>
              <p className="mt-1 max-w-md text-xs text-muted-foreground">Les réponses sont calculées par le backend sur le dataset actif.</p>
              <div className="mt-5 grid w-full max-w-2xl gap-2 sm:grid-cols-3">
                {questionSuggestions.map((question) => (
                  <button key={question} type="button" onClick={() => void send(question)} className="rounded-lg border border-border bg-card px-3 py-2.5 text-left text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-accent">
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => message.role === 'user' ? (
              <div key={index} className="flex items-start justify-end gap-3">
                <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{message.content}</div>
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary"><User className="size-4" /></span>
              </div>
            ) : (
              <div key={index} className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
                <div data-testid="assistant-message" className="max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-muted/40 px-4 py-3.5">
                  <div className="mb-2"><ModeBadge mode={message.content.mode} /></div>
                  <p className="text-sm leading-relaxed text-foreground">{message.content.summary}</p>
                  {message.content.suggestions?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.content.suggestions.map((suggestion) => (
                        <button key={suggestion} type="button" onClick={() => void send(suggestion)} className="rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/40 hover:text-primary">{suggestion}</button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
          {sending ? <div className="flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />Analyse en cours…</div> : null}
        </div>

        <div className="border-t border-border p-3">
          <div className="flex items-end gap-2">
            <Textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={onKeyDown} rows={1} placeholder="Posez une question sur le dataset…" className="max-h-32 min-h-10 resize-none" />
            <Button size="icon" className="size-10 shrink-0" disabled={sending || !input.trim()} onClick={() => void send(input)} aria-label="Envoyer la question">
              {sending ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
