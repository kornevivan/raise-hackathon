import { useEffect, useMemo, useRef, useState } from 'react'
import { getHealth, getScenarios, runScenario, runUpload, uploadDocuments, getSamples, postDecision } from './api.js'
import Trace from './Trace.jsx'
import { Memo, DocViewer, RatioBanner } from './Memo.jsx'
import UploadPanel from './UploadPanel.jsx'
import { Icon } from './ui.jsx'

export default function App() {
  const [health, setHealth] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [active, setActive] = useState(null)        // scenario id
  const [events, setEvents] = useState([])
  const [running, setRunning] = useState(false)
  const [runId, setRunId] = useState(null)
  const [memo, setMemo] = useState(null)
  const [tab, setTab] = useState('memo')            // memo | source
  const [source, setSource] = useState(null)
  const [decision, setDecision] = useState(null)
  const [mode, setMode] = useState('samples')   // samples | upload
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadErr, setUploadErr] = useState(null)
  const traceRef = useRef(null)
  const stopRef = useRef(null)

  useEffect(() => { getHealth().then(setHealth); getScenarios().then(setScenarios) }, [])
  useEffect(() => {
    if (traceRef.current) traceRef.current.scrollTop = traceRef.current.scrollHeight
  }, [events, running])

  function beginRun(activeId, streamFn) {
    stopRef.current?.()
    setActive(activeId); setEvents([]); setMemo(null); setSource(null)
    setDecision(null); setTab('memo'); setRunning(true)
    stopRef.current = streamFn({
      onRunId: setRunId,
      onTrace: (ev) => {
        setEvents((prev) => [...prev, ev])
        if (ev.kind === 'memo') setMemo(ev.payload)
      },
      onEnd: () => setRunning(false),
      onError: () => setRunning(false),
    })
  }

  function start(sc) {
    beginRun(sc.id, (h) => runScenario(sc.id, h))
  }

  async function analyze(files) {
    setUploadErr(null); setUploadBusy(true)
    try {
      const { upload_id } = await uploadDocuments(files)
      setUploadBusy(false)
      beginRun('upload:' + upload_id, (h) => runUpload(upload_id, h))
    } catch (e) {
      setUploadBusy(false); setUploadErr(e.message || 'upload failed')
    }
  }

  function openSource(s) {
    setSource({
      image: s.image, width: s.width, height: s.height,
      bbox: s.bbox ?? s.blocks?.[0]?.bbox, doc_title: s.doc_title,
      page: s.page, scanned: s.scanned, text: s.text ?? s.blocks?.[0]?.text,
    })
    setTab('source')
  }
  async function decide(action) {
    const r = await postDecision(runId, action)
    setDecision(r)
  }

  // live ratio banner derived from tool events
  const ratio = useMemo(() => {
    const calcs = events.filter((e) => e.kind === 'tool' && e.payload?.tool === 'ratio_calculator')
    if (!calcs.length) return null
    const first = calcs[0].payload.result, last = calcs[calcs.length - 1].payload.result
    const threshold = calcs[0].payload.threshold
    const twisted = (last.addback_total || 0) > 0
    return { naive: first.ratio, final: last.ratio, threshold, twisted }
  }, [events])

  const llmCalls = memo?.llm_calls ?? events.find((e) => e.kind === 'done')?.payload?.llm_calls

  return (
    <div className="flex h-screen flex-col">
      {/* header */}
      <header className="flex items-center justify-between border-b border-slate-800/80 px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-slate-950">
            <Icon name="verify" className="h-5 w-5" />
          </div>
          <div>
            <div className="text-[15px] font-semibold tracking-tight text-slate-100">Covenant Sentinel</div>
            <div className="text-[11px] text-slate-500">Agentic loan-covenant monitoring · grounded in the documents</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {llmCalls != null && (
            <span className="chip border border-slate-700 bg-slate-800/50 px-2.5 py-1 text-slate-300">{llmCalls} LLM calls</span>
          )}
          <HealthBadge health={health} />
        </div>
      </header>

      {/* mode toggle */}
      <div className="flex items-center gap-2 border-b border-slate-800/80 px-5 pt-2.5">
        <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/50 p-0.5 text-[12px]">
          <TabBtn on={mode === 'samples'} onClick={() => setMode('samples')} label="Sample portfolio" />
          <TabBtn on={mode === 'upload'} onClick={() => setMode('upload')} label="Upload your documents" />
        </div>
        <span className="text-[11px] text-slate-500">
          {mode === 'samples' ? 'Pick a borrower from the example portfolio'
                              : 'Upload a credit agreement + financials (PDF) — the agent detects the covenant and analyzes it'}
        </span>
      </div>

      {/* launcher */}
      {mode === 'samples' ? (
        <div className="flex gap-2 overflow-x-auto border-b border-slate-800/80 px-5 py-2.5">
          {scenarios.map((s) => (
            <button key={s.id} onClick={() => start(s)} disabled={running}
              className={`group min-w-[260px] flex-1 rounded-xl border px-3 py-2 text-left transition disabled:opacity-60
                ${active === s.id ? 'border-sky-500/60 bg-sky-500/5' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'}`}>
              <div className="flex items-center justify-between">
                <span className="text-[12.5px] font-semibold text-slate-100">{s.label}</span>
                <span className="chip border border-slate-700 bg-slate-800/60 text-slate-400 group-hover:text-sky-300">
                  {active === s.id && running ? 'running…' : 'run ▸'}
                </span>
              </div>
              <div className="mt-0.5 line-clamp-2 text-[11px] leading-tight text-slate-500">{s.blurb}</div>
            </button>
          ))}
        </div>
      ) : (
        <div className="border-b border-slate-800/80 px-5 py-3">
          <UploadPanel onAnalyze={analyze} busy={uploadBusy || running} error={uploadErr} />
        </div>
      )}

      {/* two panes */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
        {/* left: trace */}
        <section ref={traceRef} className="min-h-0 overflow-y-auto border-r border-slate-800/80 px-5 py-4">
          <PaneTitle icon="route" title="Agent trace" subtitle="plan → retrieve → tools → decide → verify → memo" />
          {events.length === 0 ? (
            <Empty text="Pick a borrower above to run a covenant check." />
          ) : (
            <Trace events={events} running={running} onOpen={openSource} />
          )}
        </section>

        {/* right: memo / source */}
        <section className="min-h-0 overflow-y-auto px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/50 p-0.5 text-[12px]">
              <TabBtn on={tab === 'memo'} onClick={() => setTab('memo')} label="Memo" />
              <TabBtn on={tab === 'source'} onClick={() => setTab('source')} label="Source document" />
            </div>
          </div>

          {ratio && tab === 'memo' && (
            <div className="mb-4"><RatioBanner {...ratio} /></div>
          )}

          {tab === 'memo' ? (
            memo ? (
              <Memo memo={memo} decision={decision} onCite={openSource} onDecision={decide} />
            ) : (
              <Empty text={running ? 'Analyzing… the memo appears when the agent finishes.' : 'Run a scenario to generate a decision-ready memo.'} />
            )
          ) : (
            <DocViewer source={source} />
          )}
        </section>
      </div>
    </div>
  )
}

function HealthBadge({ health }) {
  if (!health) return null
  const live = health.live_inference
  return (
    <span className={`chip border px-2.5 py-1 ${live ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/40 bg-amber-500/10 text-amber-300'}`}
      title={live ? 'Reasoning + retrieval on Vultr Serverless Inference' : 'Deterministic offline mode — set VULTR_INFERENCE_API_KEY'}>
      <span className={`h-1.5 w-1.5 rounded-full ${live ? 'bg-emerald-400' : 'bg-amber-400'}`} />
      {live ? 'Vultr inference live' : 'Offline demo mode'}
    </span>
  )
}

function TabBtn({ on, onClick, label }) {
  return (
    <button onClick={onClick} className={`rounded-md px-3 py-1 font-medium transition ${on ? 'bg-slate-700/70 text-slate-100' : 'text-slate-400 hover:text-slate-200'}`}>{label}</button>
  )
}

function PaneTitle({ icon, title, subtitle }) {
  return (
    <div className="mb-4 flex items-center gap-2">
      <span className="text-slate-500"><Icon name={icon} /></span>
      <div>
        <div className="text-[13px] font-semibold text-slate-200">{title}</div>
        <div className="text-[11px] text-slate-500">{subtitle}</div>
      </div>
    </div>
  )
}

function Empty({ text }) {
  return <div className="grid h-64 place-items-center rounded-xl border border-dashed border-slate-800 text-center text-[13px] text-slate-600">{text}</div>
}
