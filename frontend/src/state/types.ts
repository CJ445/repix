export type Tool = 'crop' | 'resize' | 'colorize' | 'upscale'

export type JobStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired'

export interface JobResponse {
  job_id: string
  status: JobStatus
  operation?: 'colorize' | 'upscale'
  scale?: 2 | 4
  download_url?: string
  error_message?: string
}

export interface EditorImage {
  /** Object URL for display */
  url: string
  /** Underlying file blob, full resolution */
  blob: Blob
  width: number
  height: number
  name: string
  mimeType: string
}

export type AppPhase =
  | 'idle'
  | 'ready'
  | 'processing'
  | 'completed'
  | 'failed'
