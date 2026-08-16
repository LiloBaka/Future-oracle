import type { Prediction } from '../types'

export function PredictionCard({ prediction }: { prediction: Prediction }) {
  const isRain = prediction.prediction_class === 'rain'
  return (
    <section className="card hero-card">
      <div className="card-heading">
        <div>
          <p className="eyebrow">Tomorrow · {prediction.target_date}</p>
          <h2>{prediction.location.name}</h2>
        </div>
        <span className={`verdict ${isRain ? 'rain' : 'dry'}`}>{isRain ? 'RAIN' : 'NO RAIN'}</span>
      </div>

      <div className="metrics-grid">
        <Metric label="Rain probability" value={`${prediction.rain_probability_pct.toFixed(1)}%`} />
        <Metric label="Confidence" value={`${prediction.confidence_pct.toFixed(1)}%`} />
        <Metric label="Risk" value={prediction.risk_level.toUpperCase()} />
        <Metric label="Algorithm" value={`v${prediction.algorithm_version}`} />
      </div>

      <p className="explanation">{prediction.explanation}</p>
      <p className="muted">Updated {new Date(prediction.created_at).toLocaleString()}</p>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
