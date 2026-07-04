export async function getHealth() {
  const r = await fetch('/api/health'); return r.json()
}
export async function getSamples() {
  try { const r = await fetch('/api/samples'); return (await r.json()).files } catch { return [] }
}
export async function uploadDocuments(fileList) {
  const fd = new FormData()
  for (const f of fileList) fd.append('files', f)
  const r = await fetch('/api/upload', { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'upload failed')
  return r.json()
}
// resolve a page image: uploaded docs use absolute /uploads/... paths
export function imgUrl(image) {
  if (!image) return ''
  return image.startsWith('/') ? image : `/corpus/${image}`
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
function stream(url, { onRunId, onTrace, onEnd, onError }) {
  const es = new EventSource(url)
  es.addEventListener('run_id', (e) => onRunId?.(JSON.parse(e.data).run_id))
  es.addEventListener('trace', (e) => onTrace?.(JSON.parse(e.data)))
  es.addEventListener('end', () => { onEnd?.(); es.close() })
  es.onerror = () => { onError?.(); es.close() }
  return () => es.close()
}
export function runScenario(scenarioId, handlers) {
  return stream(`/api/run/${scenarioId}`, handlers)
}
export function runUpload(uploadId, handlers) {
  return stream(`/api/run_upload/${uploadId}`, handlers)
}

export async function getSuggested(scenarioId) {
  try { const r = await fetch(`/api/suggested/${scenarioId}`); return (await r.json()).questions } catch { return [] }
}
export async function getChatHistory(runId) {
  try { const r = await fetch(`/api/chat/${runId}`); return (await r.json()).history } catch { return [] }
}

// POST-based SSE (EventSource is GET-only): parse the text/event-stream manually.
export async function chatStream(runId, message, { onStep, onAnswer, onEnd, onError }) {
  try {
    const resp = await fetch(`/api/chat/${runId}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!resp.ok || !resp.body) throw new Error('chat failed')
    const reader = resp.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const chunks = buf.split(/\r?\n\r?\n/)
      buf = chunks.pop()
      for (const c of chunks) {
        const ev = c.match(/event:\s*(\w+)/)?.[1]
        const data = c.match(/data:\s*([\s\S]*?)\s*$/)?.[1]
        if (!data) continue
        const parsed = JSON.parse(data)
        if (ev === 'chat') {
          if (parsed.kind === 'chat_answer') onAnswer?.(parsed)
          else onStep?.(parsed)
        } else if (ev === 'end') onEnd?.()
      }
    }
    onEnd?.()
  } catch (e) { onError?.(e) }
}
