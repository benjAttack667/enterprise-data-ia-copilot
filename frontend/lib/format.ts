const EMPTY_VALUE = '—'

export function formatNullableNumber(
  value: number | null | undefined,
  maximumFractionDigits = 2,
) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY_VALUE
  return value.toLocaleString('fr-FR', { maximumFractionDigits })
}

function formatIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?$/.test(value)) return null

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null

  return value.length === 10
    ? date.toLocaleDateString('fr-FR', { dateStyle: 'medium', timeZone: 'UTC' })
    : date.toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatDataValue(value: unknown, maximumFractionDigits = 4) {
  if (value === null || value === undefined) return EMPTY_VALUE
  if (typeof value === 'number') {
    return formatNullableNumber(value, maximumFractionDigits)
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime())
      ? EMPTY_VALUE
      : value.toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed || trimmed.toLowerCase() === 'nat') return EMPTY_VALUE
    return formatIsoDate(trimmed) ?? value
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

export function hasDisplayValue(value: unknown) {
  return formatDataValue(value) !== EMPTY_VALUE
}
