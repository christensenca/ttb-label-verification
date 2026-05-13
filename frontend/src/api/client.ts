/**
 * Thin fetch wrapper for the FastAPI backend.
 *
 * `useApi()` returns `{get, post, del}` helpers that throw on non-2xx.
 * Types are sourced from `generated.ts` (regenerated via `pnpm gen:api`).
 */

// `paths` and `operations` are imported once the generator has run; today the
// stub keeps imports cheap. Re-export so callers refer to a single module.
export type { components, operations, paths } from './generated'

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `HTTP ${status}`)
    this.status = status
    this.body = body
  }
}

async function parseOrThrow<T>(res: Response): Promise<T> {
  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  if (!res.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : undefined) ?? `HTTP ${res.status}`
    throw new ApiError(res.status, body, detail)
  }
  return body as T
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    ...init,
  })
  return parseOrThrow<T>(res)
}

async function post<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const isFormData = body instanceof FormData
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: isFormData
      ? { Accept: 'application/json' }
      : { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  })
  return parseOrThrow<T>(res)
}

async function del<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
    ...init,
  })
  // 204 No Content — return undefined as T.
  if (res.status === 204) return undefined as T
  return parseOrThrow<T>(res)
}

export const api = { get, post, del }

export function useApi() {
  return api
}
