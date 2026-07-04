import { PHASE, TierBadge, ModeBadge, Icon } from './ui.jsx'

function StepShell({ ev, children }) {
  const ph = PHASE[ev.phase] || PHASE.EVIDENCE
  return (
    <div className="step-in relative pl-9">
      <span className={`absolute left-[10px] top-1.5 h-2.5 w-2.5 rounded-full ${ph.dot} ring-4 ring-slate-950`} />
      <div className="pb-4">
        <div className="flex items-center gap-2 text-slate-200">
          <span className={ph.color}><Icon name={ev.kind} /></span>
          <span className="text-[13px] font-semibold">{ev.title}</span>
          <TierBadge tier={ev.tier} />
          <ModeBadge mode={ev.mode} />
          {ev.latency_ms ? <span className="text-[10px] text-slate-500 mono">{ev.latency_ms}ms</span> : null}
        </div>
        {children}
      </div>
    </div>
  )
}

function Hit({ h, onOpen }) {
  return (
    <button onClick={() => onOpen(h)}
      className="group flex gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-1.5 text-left hover:border-sky-500/50 transition">
      <div className="relative h-16 w-12 shrink-0 overflow-hidden rounded bg-slate-800">
        <img src={`/corpus/${h.image}`} alt="" className="h-full w-full object-cover object-top opacity-90 group-hover:opacity-100" />
        {h.scanned && <span className="absolute bottom-0 left-0 right-0 bg-amber-500/80 text-[8px] font-bold text-slate-900 text-center">SCAN</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11px] font-semibold text-slate-200">{h.doc_title}</div>
        <div className="text-[10px] text-slate-500">page {h.page} · score {h.score}</div>
        <div className="mt-0.5 line-clamp-2 text-[10px] leading-tight text-slate-400">{h.blocks?.[0]?.text}</div>
      </div>
    </button>
  )
}

function StepBody({ ev, onOpen }) {
  const p = ev.payload || {}
  switch (ev.kind) {
    case 'plan':
      return (
        <div className="mt-1.5 space-y-1.5">
          {p.checks?.map((c) => (
            <div key={c.id} className="card p-2.5 text-[12px]">
              <div className="font-semibold text-slate-100">{c.covenant_name}
                <span className="chip ml-2 border border-slate-700 bg-slate-800/60 text-slate-300">{c.risk_priority} priority</span>
              </div>
              <div className="mt-1 text-slate-400"><span className="text-slate-500">needs:</span> {c.definition_source_needed}</div>
              <div className="text-slate-400 mono text-[11px]"><span className="text-slate-500">formula:</span> {c.ratio_formula_hint}</div>
            </div>
          ))}
        </div>
      )
    case 'retrieve':
      return (
        <div className="mt-1.5">
          <div className="mb-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-[11.5px] text-slate-400">
            <span className="text-slate-500">why:</span> <span className="text-slate-300">{p.reason}</span>
            <div className="mt-1 text-slate-500 mono">query “{p.query}”</div>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {p.hits?.map((h) => <Hit key={h.page_uid} h={h} onOpen={onOpen} />)}
          </div>
        </div>
      )
    case 'tool': {
      const r = p.result || {}
      const steps = r.steps
      return (
        <div className="mt-1.5 card p-2.5 text-[11.5px]">
          <div className="text-slate-400">{ev.detail}</div>
          {steps && (
            <pre className="mt-1.5 overflow-x-auto rounded bg-slate-950/70 p-2 text-[11px] leading-relaxed text-emerald-200/90 mono">{steps.join('\n')}</pre>
          )}
          {r.rows && r.rows.length > 0 && (
            <div className="mt-1.5 space-y-0.5">
              {r.rows.slice(0, 4).map((row) => (
                <div key={row.txn_id} className="flex justify-between gap-2 text-[11px]">
                  <span className="truncate text-slate-400">{row.vendor} · {row.memo}</span>
                  <span className="mono text-slate-300">${(row.amount_usd_000/1000).toFixed(1)}M</span>
                </div>
              ))}
              <div className="flex justify-between border-t border-slate-800 pt-1 text-[11px] font-semibold">
                <span className="text-slate-300">total</span>
                <span className="mono text-amber-300">${r.total_usd_millions}M</span>
              </div>
            </div>
          )}
        </div>
      )
    }
    case 'gap': {
      const found = p.gap?.gap_found
      return (
        <div className={`mt-1.5 rounded-lg border p-2.5 text-[12px] ${found ? 'border-amber-500/40 bg-amber-500/5' : 'border-slate-800 bg-slate-900/50'}`}>
          <div className={found ? 'text-amber-200' : 'text-slate-400'}>{ev.detail}</div>
          {p.gap?.missing_document && (
            <div className="mt-1 text-[11px] text-amber-300/90">→ missing: <b>{p.gap.missing_document}</b>{p.gap.escalate_retriever ? ' · escalating retriever' : ''}</div>
          )}
        </div>
      )
    }
    case 'cause':
      return <div className="mt-1.5 rounded-lg border border-slate-800 bg-slate-900/50 p-2.5 text-[12px] text-slate-300">{ev.detail}</div>
    case 'verify': {
      const frac = p.verify?.verified_fraction ?? 1
      return (
        <div className="mt-1.5 card p-2.5 text-[12px]">
          <div className="mb-1 flex justify-between text-slate-400"><span>claims grounded</span><span className="mono text-emerald-300">{Math.round(frac*100)}%</span></div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-emerald-400" style={{ width: `${frac*100}%` }} />
          </div>
          <div className="mt-1.5 text-[11px] text-slate-500">{p.verify?.notes}</div>
        </div>
      )
    }
    case 'route':
    case 'status':
      return <div className="mt-0.5 text-[11.5px] text-slate-400">{ev.detail}</div>
    case 'done':
      return <div className="mt-0.5 text-[11.5px] text-emerald-300/90">{ev.detail}</div>
    default:
      return ev.detail ? <div className="mt-0.5 text-[11.5px] text-slate-400">{ev.detail}</div> : null
  }
}

export default function Trace({ events, running, onOpen }) {
  return (
    <div className="relative">
      <div className="absolute left-[15px] top-1 bottom-0 w-px bg-slate-800" />
      <div className="space-y-0">
        {events.map((ev) => (
          <StepShell key={ev.seq} ev={ev}><StepBody ev={ev} onOpen={onOpen} /></StepShell>
        ))}
        {running && (
          <div className="relative pl-9">
            <span className="absolute left-[10px] top-1.5 h-2.5 w-2.5 rounded-full bg-slate-500 ring-4 ring-slate-950 thinking" />
            <div className="thinking text-[12px] text-slate-500">agent working…</div>
          </div>
        )}
      </div>
    </div>
  )
}
