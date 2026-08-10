/** Limite publique côté navigateur : 10 mébioctets, soit 10 × 1 024² octets. */
export const MAX_UPLOAD_SIZE_MIB = 10
export const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MIB * 1_024 * 1_024
export const MAX_UPLOAD_SIZE_LABEL = `${MAX_UPLOAD_SIZE_MIB} Mio`

export function formatUploadSizeLabel(bytes: number) {
  const mebibytes = bytes / (1_024 * 1_024)
  if (mebibytes >= 1) {
    return `${mebibytes.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mio`
  }

  const kibibytes = bytes / 1_024
  if (kibibytes >= 1) {
    return `${kibibytes.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Kio`
  }

  return `${bytes.toLocaleString('fr-FR')} octet${bytes > 1 ? 's' : ''}`
}

// Marge réservée à la boundary et aux en-têtes multipart, pas au fichier lui-même.
export const MULTIPART_OVERHEAD_BYTES = 64 * 1_024
export const MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_SIZE_BYTES + MULTIPART_OVERHEAD_BYTES

export const SUPPORTED_UPLOAD_EXTENSIONS = ['csv', 'xlsx'] as const
export const SUPPORTED_UPLOAD_FORMATS_LABEL = 'CSV ou XLSX'

export function datasetFileExtension(filename: string) {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

export function isSupportedDatasetFile(filename: string) {
  const extension = datasetFileExtension(filename)
  return SUPPORTED_UPLOAD_EXTENSIONS.some((supported) => supported === extension)
}
