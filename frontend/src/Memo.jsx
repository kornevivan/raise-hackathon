import { useEffect, useRef } from 'react'
import { RecBadge, Icon } from './ui.jsx'

export function RatioBanner({ naive, final, threshold, twisted }) {
  if (naive == null) return null
  const overN = naive > threshold
  const overF = final > threshold
  return (
    <div className="flex items-stretch gap-3">
      <RatioTile label={twisted ? 'As reported (naive)' : 'Leverage'} value={naive} over={overN} strike={twisted} />
      {twisted && (
        <>
          <div className="flex items-center text-slate-500"><Icon name="route" className="w-5 h-5" /></div>
          <RatioTile label="After amendment addback" value={final} over={overF} flip />
        </>
      )}
      <div className="flex flex-col justify-center rounded-xl border border-slate-800 bg-slate-900/50 px-3">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">Covenant</div>
        <div className="mono text-lg font-semibold text-slate-300">≤ {threshold.toFixed(2)}x</div>
      </div>
    </div>
  )
}

function RatioTile({ label, value, over, strike, flip }) {
  return (
    <div className={`flex-1 rounded-xl border px-3 py-2 ${over ? 'border-rose-500/40 bg-rose-500/5' : 'border-emerald-500/40 bg-emerald-500/5'}`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mono text-2xl font-bold ${flip ? 'flip' : ''} ${over ? 'text-rose-300' : 'text-emerald-300'} ${strike ? 'line-through decoration-2 opacity-70' : ''}`}>
        {value.toFixed(2)}x
      </div>
    </div>
  )
}

export function Memo({ memo, onCite, onDecision, decision }) {
  if (!memo) return null
  const m = memo.memo
  // number citations by first appearance in the memo
  const order = []
  m.sections.forEach((s) => s.sentences.forEach((sn) => sn.citations.forEach((c) => {
    if (!order.includes(c)) order.push(c)
  })))
  const num = Object.fromEntries(order.map((c, i) => [c, i + 1]))
  const byId = Object.fromEntries(memo.citations.map((c) => [c.id, c]))

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <RecBadge rec={m.recommendation} />
          <span className="chip border border-slate-700 bg-slate-800/50 px-2.5 py-1 text-slate-300">
            confidence <b className="ml-1 mono text-slate-100">{Math.round(m.confidence * 100)}%</b>
          </span>
          <span className="text-[11px] text-slate-500">{memo.borrower} · {memo.period}</span>
        </div>
        <h2 className="mt-2 text-[15px] font-semibold leading-snug text-slate-100">{m.headline}</h2>
      </div>

      <div className="space-y-3">
        {m.sections.map((s, i) => (
          <div key={i}>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-300/80">{s.heading}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-slate-300">
              {s.sentences.map((sn, j) => (
                <span key={j}>
                  {sn.text}{' '}
                  {sn.citations.map((c) => (
                    <button key={c} onClick={() => onCite(byId[c])}
                      className="align-super text-[10px] font-bold text-sky-400 hover:text-sky-200 hover:underline">
                      [{num[c]}]
                    </button>
                  ))}{' '}
                </span>
              ))}
            </p>
          </div>
        ))}
      </div>

      {/* sources */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-2.5">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Sources</div>
        <div className="space-y-1">
          {order.map((c) => byId[c] && (
            <button key={c} onClick={() => onCite(byId[c])}
              className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[11.5px] hover:bg-slate-800/50">
              <span className="mono text-sky-400">[{num[c]}]</span>
              <span className="text-slate-400">{byId[c].doc_title} · p{byId[c].page}</span>
              {byId[c].scanned && <span className="chip border border-amber-500/40 bg-amber-500/10 text-amber-300">scan</span>}
            </button>
          ))}
        </div>
      </div>

      {/* human decision */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Analyst decides</div>
        {decision ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-[12px] text-emerald-200">
            <Icon name="done" className="mr-1 inline h-4 w-4" />{decision.message}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button onClick={() => onDecision('approve')} className="btn bg-emerald-500/90 text-slate-950 hover:bg-emerald-400">Approve & file</button>
            <button onClick={() => onDecision('escalate')} className="btn bg-rose-500/90 text-white hover:bg-rose-400">Escalate</button>
            <button onClick={() => onDecision('send_back')} className="btn border border-slate-700 bg-slate-800/60 text-slate-200 hover:bg-slate-700">Send back</button>
          </div>
        )}
      </div>
    </div>
  )
}

export function DocViewer({ source }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [source])
  if (!source) {
    return <div className="flex h-full items-center justify-center text-sm text-slate-600">Click a citation to view the source page.</div>
  }
  const bb = source.bbox
  const pct = bb ? {
    left: `${(bb[0] / source.width) * 100}%`, top: `${(bb[1] / source.height) * 100}%`,
    width: `${(bb[2] / source.width) * 100}%`, height: `${(bb[3] / source.height) * 100}%`,
  } : null
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-[12px] text-slate-400">
        <Icon name={source.scanned ? 'scan' : 'doc'} className="w-4 h-4 text-slate-500" />
        <span className="font-semibold text-slate-200">{source.doc_title}</span>
        <span className="text-slate-500">· page {source.page}</span>
        {source.scanned && <span className="chip border border-amber-500/40 bg-amber-500/10 text-amber-300">scanned page</span>}
      </div>
      <div className="relative overflow-hidden rounded-lg border border-slate-800 bg-white">
        <img src={`/corpus/${source.image}`} alt="" className="block w-full" />
        {pct && <div ref={ref} className="pointer-events-none absolute rounded-sm ring-2 ring-amber-400" style={{ ...pct, background: 'rgba(250,204,21,0.22)' }} />}
      </div>
    </div>
  )
}
