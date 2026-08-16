import type { Prediction } from '../types'

export function History({ predictions }: { predictions: Prediction[] }) {
  return (
    <section className="card">
      <h3>Prediction history & evaluation</h3>
      {predictions.length === 0 ? (
        <p className="muted">No predictions yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Target</th>
                <th>Prediction</th>
                <th>Probability</th>
                <th>Confidence</th>
                <th>Risk</th>
                <th>Evaluation</th>
              </tr>
            </thead>
            <tbody>
              {predictions.map((prediction) => (
                <tr key={prediction.id}>
                  <td>{new Date(prediction.created_at).toLocaleString()}</td>
                  <td>{prediction.target_date}</td>
                  <td>{prediction.prediction_class === 'rain' ? 'Rain' : 'No rain'}</td>
                  <td>{prediction.rain_probability_pct.toFixed(1)}%</td>
                  <td>{prediction.confidence_pct.toFixed(1)}%</td>
                  <td>{prediction.risk_level}</td>
                  <td>{prediction.evaluation?.status ?? 'pending'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
