import { useEffect, useRef, useState } from 'react'
import { getSuggested, getChatHistory, chatStream } from './api.js'
import { Icon, TierBadge } from './ui.jsx'

function Bubble({ turn, onCite, onAction }) {
  const isUser = turn.role === 'user'
  if (isUser) {
    return <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-sm bg-sky-500/90 px-3 py-1.5 text-[12.5px] text-slate-950">{turn.text}</div></div>
  }
  const byId = Object.fromEntries((turn.citations || []).map((c) => [c.n, c]))
  // split text on [n] markers → clickable chips
  const parts = (turn.text || '').split(/(\[\d+\])/g)
  return (
    <div className="flex flex-col gap-1">
      {turn.steps?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {turn.steps.map((s, i) => (
            <span key={i} className="chip border border-slate-700 bg-slate-800/50 text-[10px] text-slate-400">
              <TierBadge tier={s.tier} />{s.label}
            </span>
          ))}
        </div>
      )}
      <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/70 px-3 py-2 text-[12.5px] leading-relaxed text-slate-200">
        {turn.hypothetical && <span className="chip mr-1 border border-amber-400/40 bg-amber-500/10 text-amber-200">HYPOTHETICAL</span>}
        {parts.map((p, i) => {
          const m = p.match(/^\[(\d+)\]$/)
          if (m && byId[+m[1]]) return <button key={i} onClick={() => onCite(byId[+m[1]])} className="align-super text-[10px] font-bold text-sky-400 hover:text-sky-200">[{m[1]}]</button>
          return <span key={i}>{p}</span>
        })}
        {turn.action?.run && (
          <div className="mt-2">
            <button onClick={() => onAction(turn.action)} className="btn border border-sky-500/50 bg-sky-500/10 px-2.5 py-1 text-[11px] text-sky-200 hover:bg-sky-500/20">
              {turn.action.label} →
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Chat({ runId, scenarioId, onCite, onAction }) {
  const [turns, setTurns] = useState([])
  const [suggested, setSuggested] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { getSuggested(scenarioId).then(setSuggested) }, [scenarioId])
  useEffect(() => { if (runId) getChatHistory(runId).then((h) => setTurns(h || [])) }, [runId])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])

  async function send(text) {
    const q = (text ?? input).trim()
    if (!q || busy || !runId) return
    setInput(''); setBusy(true)
    setTurns((t) => [...t, { role: 'user', text: q }, { role: 'assistant', text: '', steps: [], citations: [] }])
    await chatStream(runId, q, {
      onStep: (s) => setTurns((t) => { const c = [...t]; const a = c[c.length - 1]; a.steps = [...(a.steps || []), s]; return c }),
      onAnswer: (a) => setTurns((t) => { const c = [...t]; c[c.length - 1] = { role: 'assistant', ...a }; return c }),
      onEnd: () => setBusy(false),
      onError: () => setBusy(false),
    })
  }

  if (!runId) {
    return <div className="grid h-64 place-items-center text-center text-[13px] text-slate-600">Run a scenario, then ask questions about it here.</div>
  }
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {turns.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-800 p-3 text-[12px] text-slate-500">
            Ask about this run — cap math, the step-down, precedents, or a what-if. Every answer is cited and every number is tool-computed.
          </div>
        )}
        {turns.map((t, i) => <Bubble key={i} turn={t} onCite={onCite} onAction={onAction} />)}
        {busy && <div className="thinking text-[11px] text-slate-500">thinking…</div>}
        <div ref={endRef} />
      </div>

      {suggested.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {suggested.map((q) => (
            <button key={q} onClick={() => send(q)} disabled={busy}
              className="chip border border-slate-700 bg-slate-800/40 text-[11px] text-slate-300 hover:border-sky-500/50 hover:text-sky-200 disabled:opacity-50">{q}</button>
          ))}
        </div>
      )}
      <div className="mt-2 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Ask about this run…" disabled={busy}
          className="flex-1 rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-[12.5px] text-slate-200 outline-none focus:border-sky-500/50" />
        <button onClick={() => send()} disabled={busy || !input.trim()} className="btn bg-sky-500 px-3 text-slate-950 hover:bg-sky-400 disabled:opacity-40"><Icon name="route" className="h-4 w-4" /></button>
      </div>
    </div>
  )
}
