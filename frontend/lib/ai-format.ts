export function formatTokenCount(value: number) {
  const normalized = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
  return normalized.toLocaleString('fr-FR')
}

export function formatUsdEstimate(value: number) {
  const normalized = Number.isFinite(value) ? Math.max(0, value) : 0
  if (normalized > 0 && normalized < 0.000001) return '< 0,000001 $US'
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'USD',
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 6,
    maximumFractionDigits: 6,
  }).format(normalized)
}

export function formatQuotaWindow(seconds: number) {
  const normalized = Number.isFinite(seconds) ? Math.max(1, Math.ceil(seconds)) : 1
  if (normalized < 60) return `${normalized} s`
  if (normalized % 3_600 === 0) {
    const hours = normalized / 3_600
    return `${hours} h`
  }
  return `${Math.ceil(normalized / 60)} min`
}

export function formatRetryDelay(seconds?: number) {
  if (seconds === undefined) return 'dans quelques minutes'
  const normalized = Math.max(1, Math.ceil(seconds))
  if (normalized < 60) {
    return `dans ${normalized} seconde${normalized > 1 ? 's' : ''}`
  }
  const minutes = Math.ceil(normalized / 60)
  return `dans environ ${minutes} minute${minutes > 1 ? 's' : ''}`
}
