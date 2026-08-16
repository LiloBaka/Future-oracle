import type { Location, Prediction } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

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
