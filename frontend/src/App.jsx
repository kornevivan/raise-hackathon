import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getHealth, getScenarios, runScenario, runUpload, uploadDocuments,
  getSuggested, chatStream, postDecision,
} from './api.js'
import Trace from './Trace.jsx'
import { Memo, DocViewer, RatioBanner } from './Memo.jsx'
import { Bubble } from './Chat.jsx'
import { Icon } from './ui.jsx'

// A "conversation" is a thread of turns: user | run (inline trace+memo) | assistant.
export default function App() {
  const [health, setHealth] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [convs, setConvs] = useState({})        // key -> conversation
  const [activeKey, setActiveKey] = useState(null)
  const [source, setSource] = useState(null)    // right drawer
  const [suggested, setSuggested] = useState({})
  const threadRef = useRef(null)
  const stopRef = useRef(null)

  useEffect(() => {
    getHealth().then(setHealth)
    getScenarios().then((scs) => {
      setScenarios(scs)
      const map = {}
      for (const s of scs) map[s.id] = freshScenarioConv(s)
      map['new'] = { key: 'new', kind: 'upload', title: 'New analysis', turns: [], files: [], started: false, running: false }
      setConvs(map)
      setActiveKey(scs[0]?.id || 'new')
    })
  }, [])

  const conv = convs[activeKey]
  useEffect(() => { if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight }, [conv])

  function patch(key, fn) {
    setConvs((c) => ({ ...c, [key]: fn(c[key]) }))
  }
  function pushTurn(key, turn) { patch(key, (c) => ({ ...c, turns: [...c.turns, turn] })) }
  function patchLastTurn(key, fn) {
    patch(key, (c) => { const t = [...c.turns]; t[t.length - 1] = fn(t[t.length - 1]); return { ...c, turns: t } })
  }

  function openSource(s) {
    setSource({
      image: s.image, width: s.width, height: s.height,
      bbox: s.bbox ?? s.blocks?.[0]?.bbox, doc_title: s.doc_title,
      page: s.page, scanned: s.scanned, text: s.text ?? s.blocks?.[0]?.text,
    })
  }

  // -- run a scenario / upload as the first assistant "run" turn --
  function startRun(key, streamFn, userText) {
    stopRef.current?.()
    pushTurn(key, { role: 'user', text: userText })
    pushTurn(key, { role: 'run', events: [], running: true, memo: null, decision: null })
    patch(key, (c) => ({ ...c, running: true, started: true }))
    stopRef.current = streamFn({
      onRunId: (rid) => patch(key, (c) => ({ ...c, runId: rid })),
      onTrace: (ev) => {
        patchLastTurn(key, (t) => ({ ...t, events: [...t.events, ev], memo: ev.kind === 'memo' ? ev.payload : t.memo }))
      },
      onEnd: () => {
        patch(key, (c) => ({ ...c, running: false }))
        patchLastTurn(key, (t) => ({ ...t, running: false }))
        const sid = convs[key]?.scenarioId
        if (sid && !suggested[sid]) getSuggested(sid).then((q) => setSuggested((s) => ({ ...s, [sid]: q })))
      },
      onError: () => { patch(key, (c) => ({ ...c, running: false })); patchLastTurn(key, (t) => ({ ...t, running: false })) },
    })
  }

  async function send(text, files) {
    const c = convs[activeKey]
    if (!c || c.running) return
    if (!c.started) {
      if (c.kind === 'scenario') {
        startRun(c.key, (h) => runScenario(c.scenarioId, h), text || c.prompt)
      } else {
        const fl = files || c.files
        if (!fl?.length) return
        pushTurn(c.key, { role: 'user', text: text || 'Analyze these documents.', docChips: fl.map((f) => f.name) })
        pushTurn(c.key, { role: 'run', events: [], running: true, memo: null, decision: null })
        patch(c.key, (x) => ({ ...x, running: true, started: true }))
        try {
          const { upload_id } = await uploadDocuments(fl)
          stopRef.current = runUpload(upload_id, {
            onRunId: (rid) => patch(c.key, (x) => ({ ...x, runId: rid })),
            onTrace: (ev) => patchLastTurn(c.key, (t) => ({ ...t, events: [...t.events, ev], memo: ev.kind === 'memo' ? ev.payload : t.memo })),
            onEnd: () => { patch(c.key, (x) => ({ ...x, running: false })); patchLastTurn(c.key, (t) => ({ ...t, running: false })) },
            onError: () => { patch(c.key, (x) => ({ ...x, running: false })); patchLastTurn(c.key, (t) => ({ ...t, running: false })) },
          })
        } catch (e) {
          patchLastTurn(c.key, (t) => ({ ...t, running: false, error: e.message }))
          patch(c.key, (x) => ({ ...x, running: false }))
        }
      }
      return
    }
    // follow-up chat turn
    if (!c.runId || !text?.trim()) return
    pushTurn(c.key, { role: 'user', text })
    pushTurn(c.key, { role: 'assistant', text: '', steps: [], citations: [] })
    patch(c.key, (x) => ({ ...x, running: true }))
    await chatStream(c.runId, text, {
      onStep: (s) => patchLastTurn(c.key, (t) => ({ ...t, steps: [...(t.steps || []), s] })),
      onAnswer: (a) => patchLastTurn(c.key, () => ({ role: 'assistant', ...a })),
      onEnd: () => patch(c.key, (x) => ({ ...x, running: false })),
      onError: () => patch(c.key, (x) => ({ ...x, running: false })),
    })
  }

  function handleAction(action) {
    if (action?.run && convs[action.run]) { setActiveKey(action.run); setTimeout(() => startRun(action.run, (h) => runScenario(action.run, h), convs[action.run].prompt), 60) }
  }
  async function decide(runTurnIdx, action) {
    const c = convs[activeKey]
    if (!c?.runId) return
    const r = await postDecision(c.runId, action)
    patch(c.key, (x) => { const t = [...x.turns]; t[runTurnIdx] = { ...t[runTurnIdx], decision: r }; return { ...x, turns: t } })
  }
  function resetConv(key) {
    const s = scenarios.find((x) => x.id === key)
    patch(key, () => (s ? freshScenarioConv(s) : { key: 'new', kind: 'upload', title: 'New analysis', turns: [], files: [], started: false, running: false }))
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-800/80 px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-slate-950"><Icon name="verify" className="h-5 w-5" /></div>
          <div>
            <div className="text-[15px] font-semibold tracking-tight text-slate-100">Covenant Sentinel</div>
            <div className="text-[11px] text-slate-500">Agentic loan-covenant analyst · grounded in the documents</div>
          </div>
        </div>
        <HealthBadge health={health} />
      </header>

      <div className="grid min-h-0 flex-1" style={{ gridTemplateColumns: source ? '250px 1fr 44%' : '250px 1fr' }}>
        {/* rail */}
        <aside className="min-h-0 overflow-y-auto border-r border-slate-800/80 p-2">
          <button onClick={() => { setActiveKey('new'); resetConv('new') }}
            className="mb-2 flex w-full items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/50 px-3 py-2 text-[12.5px] font-semibold text-slate-200 hover:border-sky-500/50">
            <Icon name="doc" className="h-4 w-4" /> New analysis (upload)
          </button>
          <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Sample analyses</div>
          {scenarios.map((s) => (
            <button key={s.id} onClick={() => setActiveKey(s.id)}
              className={`mb-1 w-full rounded-lg px-3 py-2 text-left transition ${activeKey === s.id ? 'bg-sky-500/10 ring-1 ring-sky-500/40' : 'hover:bg-slate-800/50'}`}>
              <div className="text-[12.5px] font-semibold text-slate-100">{s.label}</div>
              <div className="line-clamp-1 text-[10.5px] text-slate-500">{s.blurb}</div>
            </button>
          ))}
        </aside>

        {/* thread */}
        <section className="flex min-h-0 flex-col">
          <div ref={threadRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
            {conv && conv.turns.length === 0 && <Intro conv={conv} />}
            {conv?.turns.map((t, i) => (
              <TurnView key={i} turn={t} idx={i} onCite={openSource} onAction={handleAction}
                onDecision={(a) => decide(i, a)} />
            ))}
          </div>
          {conv && <Composer conv={conv} suggested={suggested[conv.scenarioId] || []} onSend={send}
            onReset={() => resetConv(conv.key)} />}
        </section>

        {/* source drawer */}
        {source && (
          <aside className="min-h-0 overflow-y-auto border-l border-slate-800/80 p-4">
            <div className="mb-2 flex justify-end"><button onClick={() => setSource(null)} className="chip border border-slate-700 bg-slate-800/60 text-slate-300">close ✕</button></div>
            <DocViewer source={source} />
          </aside>
        )}
      </div>
    </div>
  )
}

function freshScenarioConv(s) {
  return { key: s.id, kind: 'scenario', scenarioId: s.id, title: s.label, prompt: s.prompt,
           docLabels: s.doc_labels || [], turns: [], started: false, running: false }
}

function Intro({ conv }) {
  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-dashed border-slate-800 p-5 text-center">
      <div className="text-[14px] font-semibold text-slate-200">{conv.title}</div>
      <div className="mt-1 text-[12px] text-slate-500">
        {conv.kind === 'scenario'
          ? 'Documents are attached and the request is ready below — press Send to run the agent, then keep asking questions.'
          : 'Attach a credit agreement + financials (PDF) below and press Send. The agent detects the covenant and analyzes it.'}
      </div>
    </div>
  )
}

function TurnView({ turn, idx, onCite, onAction, onDecision }) {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-sky-500/90 px-3.5 py-2 text-[13px] text-slate-950">
          {turn.text}
          {turn.docChips?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {turn.docChips.map((d, i) => <span key={i} className="chip bg-sky-900/40 text-[10px] text-sky-950">{d}</span>)}
            </div>
          )}
        </div>
      </div>
    )
  }
  if (turn.role === 'run') return <RunTurn turn={turn} idx={idx} onCite={onCite} onAction={onAction} onDecision={onDecision} />
  return <div className="max-w-[95%]"><Bubble turn={turn} onCite={onCite} onAction={onAction} /></div>
}

function RunTurn({ turn, idx, onCite, onAction, onDecision }) {
  const [showTrace, setShowTrace] = useState(true)
  const ratio = useMemo(() => {
    const calcs = turn.events.filter((e) => e.kind === 'tool' && e.payload?.tool === 'ratio_calculator')
    if (!calcs.length) return null
    const first = calcs[0].payload.result, last = calcs[calcs.length - 1].payload.result
    return { naive: first.ratio, final: last.ratio, threshold: calcs[0].payload.threshold, twisted: last.ratio !== first.ratio }
  }, [turn.events])
  return (
    <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/40 p-3">
      <button onClick={() => setShowTrace((v) => !v)} className="flex items-center gap-2 text-[12px] font-semibold text-slate-300">
        <Icon name="route" className="h-4 w-4 text-slate-500" /> Agent trace {turn.running && <span className="thinking text-sky-400">· working…</span>}
        <span className="text-slate-500">{showTrace ? '▾' : '▸'}</span>
      </button>
      {showTrace && (
        <div className="max-h-[420px] overflow-y-auto rounded-xl bg-slate-950/40 p-3">
          <Trace events={turn.events} running={turn.running} onOpen={onCite} />
        </div>
      )}
      {ratio && <RatioBanner {...ratio} />}
      {turn.error && <div className="text-[12px] text-rose-300">{turn.error}</div>}
      {turn.memo && <div className="border-t border-slate-800 pt-3"><Memo memo={turn.memo} decision={turn.decision} onCite={onCite} onDecision={onDecision} onAction={onAction} /></div>}
    </div>
  )
}

function Composer({ conv, suggested, onSend, onReset }) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const inputRef = useRef(null)
  useEffect(() => { setText(!conv.started && conv.kind === 'scenario' ? conv.prompt : ''); setFiles([]) }, [conv.key, conv.started])
  const canSend = conv.started ? text.trim() : (conv.kind === 'scenario' || files.length)
  return (
    <div className="border-t border-slate-800/80 px-5 py-3">
      {!conv.started && conv.kind === 'scenario' && conv.docLabels?.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-500">Attached:</span>
          {conv.docLabels.map((d, i) => <span key={i} className="chip border border-slate-700 bg-slate-800/50 text-[10.5px] text-slate-300"><Icon name="doc" className="h-3 w-3" />{d}</span>)}
        </div>
      )}
      {!conv.started && conv.kind === 'upload' && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <input ref={inputRef} type="file" multiple accept=".pdf,.txt,.md,.csv" className="hidden"
            onChange={(e) => setFiles((f) => [...f, ...[...e.target.files].filter((x) => !f.some((y) => y.name === x.name))])} />
          <button onClick={() => inputRef.current?.click()} className="chip border border-slate-700 bg-slate-800/60 text-slate-200 hover:border-sky-500/50"><Icon name="doc" className="h-3.5 w-3.5" /> Attach PDFs</button>
          {files.map((f, i) => <span key={i} className="chip border border-slate-700 bg-slate-800/50 text-[10.5px] text-slate-300">{f.name}<button className="ml-1 text-slate-500 hover:text-rose-300" onClick={() => setFiles(files.filter((_, j) => j !== i))}>✕</button></span>)}
        </div>
      )}
      {conv.started && suggested.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {suggested.map((q) => <button key={q} disabled={conv.running} onClick={() => onSend(q)} className="chip border border-slate-700 bg-slate-800/40 text-[11px] text-slate-300 hover:border-sky-500/50 hover:text-sky-200 disabled:opacity-50">{q}</button>)}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={conv.started ? 1 : 2}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (canSend && !conv.running) { onSend(text, files); setText(''); setFiles([]) } } }}
          placeholder={conv.started ? 'Ask about this run…' : conv.kind === 'upload' ? 'Optional note, then Send…' : 'Edit the request or just press Send…'}
          className="flex-1 resize-none rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-[13px] text-slate-200 outline-none focus:border-sky-500/50" />
        {conv.started && <button onClick={onReset} title="Restart this analysis" className="btn border border-slate-700 bg-slate-800/60 px-2 text-slate-400 hover:text-slate-200">↻</button>}
        <button onClick={() => { if (canSend && !conv.running) { onSend(text, files); setText(''); setFiles([]) } }} disabled={!canSend || conv.running}
          className="btn bg-sky-500 px-4 text-slate-950 hover:bg-sky-400 disabled:opacity-40">
          {conv.running ? '…' : conv.started ? 'Send' : 'Send ▸ run'}
        </button>
      </div>
    </div>
  )
}

function HealthBadge({ health }) {
  if (!health) return null
  const live = health.live_inference
  return (
    <span className={`chip border px-2.5 py-1 font-semibold ${live ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}`}
      title={live ? 'LIVE — reasoning on Vultr Serverless Inference, retrieval on VultronRetriever' : 'REPLAY — deterministic offline mode'}>
      <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-emerald-400' : 'bg-amber-400'}`} />
      {live ? 'LIVE · Vultr' : 'REPLAY · offline'}
      {health.version && <span className="ml-1 font-normal opacity-60">{health.version}</span>}
    </span>
  )
}
