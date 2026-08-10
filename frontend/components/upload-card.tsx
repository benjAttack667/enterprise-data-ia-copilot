'use client'

import { UploadCloud } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { DatasetUploadButton } from '@/components/dataset-upload'
import { useDataset } from '@/components/dataset-provider'
import { SUPPORTED_UPLOAD_FORMATS_LABEL } from '@/lib/upload-constraints'

export function UploadCard() {
  const { uploadMaxLabel } = useDataset()

  return (
    <Card className="border-dashed p-6">
      <div className="flex flex-col items-center justify-center gap-3 py-6 text-center">
        <span className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <UploadCloud className="size-6" />
        </span>
        <div>
          <p className="text-sm font-medium text-foreground">Importer un nouveau dataset</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {SUPPORTED_UPLOAD_FORMATS_LABEL} · {uploadMaxLabel} maximum par import.
          </p>
        </div>
        <DatasetUploadButton />
      </div>
    </Card>
  )
}
