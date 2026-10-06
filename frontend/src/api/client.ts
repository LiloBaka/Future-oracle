import type { Location, Prediction } from '../types'

// Production defaults to the same-origin Cloudflare Pages Function at /api.
// VITE_API_URL remains available as an optional override for special deployments.
const API_URL = (import.meta.env.VITE_API_URL?.trim() || '/api').replace(/\/+$/, '')

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    throw new Error(detail || `HTTP ${response.status}`)
  }

  return response.json() as Promise<T>
}

export const api = {
  locations: () => request<Location[]>('/locations'),
  createLocation: (query: string) =>
    request<Location>('/locations', { method: 'POST', body: JSON.stringify({ query }) }),
  refresh: (id: number) =>
    request<{ status: string; prediction: Prediction; source_errors: Record<string, string> }>(
      `/locations/${id}/refresh`,
      { method: 'POST' },
    ),
  predictions: (locationId?: number) =>
    request<Prediction[]>(`/predictions${locationId ? `?location_id=${locationId}` : ''}`),
  evaluate: (id: number) => request(`/predictions/${id}/evaluate`, { method: 'POST' }),
}
