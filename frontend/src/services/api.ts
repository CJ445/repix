import type { JobResponse } from '../state/types'

const API_BASE = '/api'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = await res.json()
      if (body?.detail) message = body.detail
    } catch {
      // ignore parse failure, use default message
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

export async function createColorizeJob(file: Blob, filename: string): Promise<JobResponse> {
  const form = new FormData()
  form.append('file', file, filename)
  form.append('operation', 'colorize')
  const res = await fetch(`${API_BASE}/jobs`, { method: 'POST', body: form })
  return handle<JobResponse>(res)
}

export async function createUpscaleJob(
  file: Blob,
  filename: string,
  scale: 2 | 4
): Promise<JobResponse> {
  const form = new FormData()
  form.append('file', file, filename)
  form.append('operation', 'upscale')
  form.append('options', JSON.stringify({ scale }))
  const res = await fetch(`${API_BASE}/jobs`, { method: 'POST', body: form })
  return handle<JobResponse>(res)
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`)
  return handle<JobResponse>(res)
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${API_BASE}/jobs/${jobId}`, { method: 'DELETE' })
}

export function downloadJobUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/download`
}

export async function pollJobUntilDone(
  jobId: string,
  intervalMs: number,
  onUpdate: (job: JobResponse) => void,
  signal?: AbortSignal
): Promise<JobResponse> {
  while (true) {
    if (signal?.aborted) throw new Error('cancelled')
    const job = await getJob(jobId)
    onUpdate(job)
    if (['completed', 'failed', 'cancelled', 'expired'].includes(job.status)) {
      return job
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
