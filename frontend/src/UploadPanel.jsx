import { useEffect, useRef, useState } from 'react'
import { getSamples } from './api.js'
import { Icon } from './ui.jsx'

export default function UploadPanel({ onAnalyze, busy, error }) {
  const [files, setFiles] = useState([])
  const [samples, setSamples] = useState([])
  const [drag, setDrag] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => { getSamples().then(setSamples) }, [])

  function add(list) {
    const ok = [...list].filter((f) => /\.(pdf|txt|md|csv)$/i.test(f.name))
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size))
      return [...prev, ...ok.filter((f) => !seen.has(f.name + f.size))]
    })
  }

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_260px]">
      {/* dropzone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-5 text-center transition
          ${drag ? 'border-sky-500 bg-sky-500/10' : 'border-slate-700 bg-slate-900/40 hover:border-slate-600'}`}>
        <input ref={inputRef} type="file" multiple accept=".pdf,.txt,.md,.csv" className="hidden"
          onChange={(e) => add(e.target.files)} />
        <Icon name="doc" className="mb-1 h-6 w-6 text-slate-500" />
        <div className="text-[13px] font-semibold text-slate-200">Drop documents here or click to browse</div>
        <div className="text-[11px] text-slate-500">Credit agreement, amendment, financial statements — PDF (or .txt/.md/.csv)</div>

        {files.length > 0 && (
          <div className="mt-3 flex w-full flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
            {files.map((f, i) => (
              <span key={i} className="chip border border-slate-700 bg-slate-800/70 text-slate-300">
                <Icon name="doc" className="h-3 w-3" /> {f.name}
                <button className="ml-1 text-slate-500 hover:text-rose-300"
                  onClick={() => setFiles(files.filter((_, j) => j !== i))}>✕</button>
              </span>
            ))}
          </div>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); files.length && onAnalyze(files) }}
          disabled={busy || files.length === 0}
          className="btn mt-3 bg-sky-500 text-slate-950 hover:bg-sky-400 disabled:opacity-40">
          {busy ? 'Analyzing…' : `Analyze ${files.length || ''} document${files.length === 1 ? '' : 's'}`}
        </button>
        {error && <div className="mt-2 text-[11px] text-rose-300">{error}</div>}
      </div>

      {/* sample docs */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-2.5">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          No documents handy? Try the samples
        </div>
        <div className="space-y-1">
          {samples.map((s) => (
            <a key={s.name} href={s.url} download
              className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[11.5px] text-sky-300 hover:bg-slate-800/50">
              <Icon name="doc" className="h-3.5 w-3.5" /> {s.name}
            </a>
          ))}
        </div>
        <div className="mt-2 text-[10.5px] leading-tight text-slate-600">
          Download all three, then drop them in — they reproduce the amendment twist so you can
          see the agent catch a false positive on real files.
        </div>
      </div>
    </div>
  )
}
