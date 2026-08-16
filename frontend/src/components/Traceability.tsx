import type { Prediction } from '../types'

const fmt = (value: number | null, suffix = '') => (value == null ? '—' : `${value.toFixed(2)}${suffix}`)

export function Traceability({ prediction }: { prediction: Prediction }) {
  return (
    <div className="trace-grid">
      <section className="card">
        <h3>Sources → normalized metrics</h3>
        <div className="source-list">
          {prediction.sources.map((source) => (
            <div className="source" key={source.normalized_metric_id}>
              <strong>{source.source_code}</strong>
              <span>Raw #{source.raw_record_id} → Metric #{source.normalized_metric_id}</span>
              <span>Rain: {fmt(source.rain_amount_mm, ' mm')}</span>
              <span>Probability: {fmt(source.precipitation_probability_pct, '%')}</span>
              <span>Humidity: {fmt(source.humidity_pct, '%')}</span>
              <span>Cloud: {fmt(source.cloud_cover_pct, '%')}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>Scoring factors</h3>
        <div className="factor-list">
          {prediction.factors.map((factor) => (
            <div className="factor" key={factor.code}>
              <div>
                <strong>{factor.label}</strong>
                <span>raw {fmt(factor.raw_value)} · normalized {factor.normalized_value.toFixed(3)}</span>
              </div>
              <div className="factor-math">
                {factor.effective_weight.toFixed(3)} × {factor.normalized_value.toFixed(3)} ={' '}
                <strong>{factor.contribution.toFixed(3)}</strong>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
