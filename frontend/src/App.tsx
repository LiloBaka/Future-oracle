import { FormEvent, useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import { History } from './components/History'
import { PredictionCard } from './components/PredictionCard'
import { Traceability } from './components/Traceability'
import type { Location, Prediction } from './types'

export default function App() {
  const [locations, setLocations] = useState<Location[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [query, setQuery] = useState('Berlin')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const latest = useMemo(() => predictions[0] ?? null, [predictions])

  useEffect(() => {
    api.locations()
      .then((items) => {
        setLocations(items)
        if (items.length) setSelectedId(items[0].id)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setPredictions([])
      return
    }
    api.predictions(selectedId).then(setPredictions).catch((err: Error) => setError(err.message))
  }, [selectedId])

  async function addCity(event: FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const location = await api.createLocation(query.trim())
      setLocations((items) => (items.some((item) => item.id === location.id) ? items : [...items, location]))
      setSelectedId(location.id)
      const refreshed = await api.refresh(location.id)
      setPredictions([refreshed.prediction])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  async function refresh() {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      await api.refresh(selectedId)
      setPredictions(await api.predictions(selectedId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Deterministic weather oracle</p>
          <h1>Future Oracle</h1>
          <p>Will it rain tomorrow? Every number is traceable to stored source data.</p>
        </div>
      </header>

      <section className="toolbar card">
        <form onSubmit={addCity}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="City, e.g. Berlin" />
          <button disabled={loading}>{loading ? 'Working…' : 'Add & forecast'}</button>
        </form>
        <div className="city-controls">
          <select
            value={selectedId ?? ''}
            onChange={(event) => setSelectedId(Number(event.target.value) || null)}
          >
            <option value="">Select city</option>
            {locations.map((location) => (
              <option value={location.id} key={location.id}>
                {location.name}{location.country_code ? ` (${location.country_code})` : ''}
              </option>
            ))}
          </select>
          <button className="secondary" disabled={!selectedId || loading} onClick={refresh}>Refresh sources</button>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      {latest ? (
        <>
          <PredictionCard prediction={latest} />
          <Traceability prediction={latest} />
          <History predictions={predictions} />
        </>
      ) : (
        <section className="card empty">
          <h2>No prediction yet</h2>
          <p>Add a city or select an existing city and refresh its weather sources.</p>
        </section>
      )}
    </main>
  )
}
