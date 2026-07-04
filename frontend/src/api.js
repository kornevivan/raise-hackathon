export async function getHealth() {
  const r = await fetch('/api/health'); return r.json()
}
export async function getScenarios() {
  const r = await fetch('/api/scenarios'); return (await r.json()).scenarios
}
export async function postDecision(run_id, action, note = '') {
  const r = await fetch('/api/decision', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id, action, note }),
  })
  return r.json()
}

// Stream a run via SSE. Calls handlers as events arrive.
export function runScenario(scenarioId, { onRunId, onTrace, onEnd, onError }) {
  const es = new EventSource(`/api/run/${scenarioId}`)
  es.addEventListener('run_id', (e) => onRunId?.(JSON.parse(e.data).run_id))
  es.addEventListener('trace', (e) => onTrace?.(JSON.parse(e.data)))
  es.addEventListener('end', () => { onEnd?.(); es.close() })
  es.onerror = () => { onError?.(); es.close() }
  return () => es.close()
}
