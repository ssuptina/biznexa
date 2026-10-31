const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const inFlightGetRequests = new Map<string, Promise<unknown>>()

export class ApiRequestError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.detail = detail
  }
}

function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  return fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  }).then(async (response) => {
    const body = await response.json().catch(() => ({})) as unknown

    if (!response.ok) {
      const rawDetail = typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail?: unknown }).detail
        : undefined
      const detail = typeof rawDetail === 'object' && rawDetail !== null && 'detail' in rawDetail
        ? (rawDetail as { detail?: unknown }).detail
        : rawDetail
      const message = typeof detail === 'string' ? detail : `Request failed with status ${response.status}`
      throw new ApiRequestError(message, response.status, rawDetail)
    }

    return body as T
  })
}

export function apiGet<T>(path: string): Promise<T> {
  const existing = inFlightGetRequests.get(path)
  if (existing) return existing.then((body) => body as T)

  const request = requestJson<unknown>(path)

  inFlightGetRequests.set(path, request)
  void request.then(
    () => { if (inFlightGetRequests.get(path) === request) inFlightGetRequests.delete(path) },
    () => { if (inFlightGetRequests.get(path) === request) inFlightGetRequests.delete(path) },
  )
  return request.then((body) => body as T)
}

export function apiPost<TBody, TResponse>(path: string, body: TBody): Promise<TResponse> {
  return requestJson<TResponse>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}