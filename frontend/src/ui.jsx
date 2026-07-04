// Small shared presentational helpers.

export const PHASE = {
  PLAN:     { label: 'Plan',     color: 'text-sky-300',     ring: 'ring-sky-500/30',     dot: 'bg-sky-400' },
  EVIDENCE: { label: 'Evidence', color: 'text-indigo-300',  ring: 'ring-indigo-500/30',  dot: 'bg-indigo-400' },
  VERIFY:   { label: 'Verify',   color: 'text-emerald-300', ring: 'ring-emerald-500/30', dot: 'bg-emerald-400' },
  MEMO:     { label: 'Memo',     color: 'text-amber-300',   ring: 'ring-amber-500/30',   dot: 'bg-amber-400' },
}

export function TierBadge({ tier }) {
  if (!tier) return null
  const map = {
    flash: ['Flash', 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'],
    core:  ['Core',  'bg-violet-500/15 text-violet-300 border-violet-500/30'],
    prime: ['Prime', 'bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/30'],
  }
  const [label, cls] = map[tier] || [tier, 'bg-slate-700 text-slate-200']
  return <span className={`chip border ${cls}`}>◆ {label}</span>
}

export function ModeBadge({ mode }) {
  if (!mode) return null
  const map = {
    vultr:   ['Vultr', 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'],
    offline: ['deterministic', 'bg-slate-700/40 text-slate-300 border-slate-600/40'],
    code:    ['tool', 'bg-slate-700/40 text-slate-300 border-slate-600/40'],
    local:   ['local', 'bg-slate-700/40 text-slate-300 border-slate-600/40'],
  }
  const [label, cls] = map[mode] || [mode, 'bg-slate-700 text-slate-200']
  return <span className={`chip border ${cls}`}>{label}</span>
}

export function Icon({ name, className = 'w-4 h-4' }) {
  const p = {
    plan:     <path d="M4 5h16M4 12h10M4 19h7" />,
    retrieve: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>,
    tool:     <path d="M14 6a3 3 0 10-4 4L4 16v4h4l6-6a3 3 0 004-4z" />,
    gap:      <><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9L2 18a2 2 0 001.7 3h16.6A2 2 0 0022 18L13.7 3.9a2 2 0 00-3.4 0z" /></>,
    cause:    <><circle cx="12" cy="12" r="9" /><path d="M12 8v4l3 2" /></>,
    verify:   <><path d="M20 6L9 17l-5-5" /></>,
    memo:     <><path d="M6 3h9l5 5v13H6z" /><path d="M14 3v6h6" /></>,
    done:     <><circle cx="12" cy="12" r="9" /><path d="M8 12l3 3 5-6" /></>,
    route:    <path d="M4 17V7a2 2 0 012-2h6l2 2h4a2 2 0 012 2v8" />,
    status:   <circle cx="12" cy="12" r="4" />,
    doc:      <><path d="M6 3h9l5 5v13H6z" /><path d="M14 3v6h6" /></>,
    scan:     <><path d="M4 7V5a1 1 0 011-1h2M17 4h2a1 1 0 011 1v2M20 17v2a1 1 0 01-1 1h-2M7 20H5a1 1 0 01-1-1v-2" /><path d="M4 12h16" /></>,
  }[name] || <circle cx="12" cy="12" r="4" />
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className={className}>{p}</svg>
  )
}

export function RecBadge({ rec }) {
  const map = {
    false_positive: ['False positive avoided', 'bg-amber-500/15 text-amber-200 border-amber-400/40'],
    no_breach:      ['In compliance', 'bg-emerald-500/15 text-emerald-200 border-emerald-400/40'],
    breach:         ['Breach', 'bg-rose-500/15 text-rose-200 border-rose-400/40'],
    at_risk:        ['At risk', 'bg-orange-500/15 text-orange-200 border-orange-400/40'],
    insufficient_data: ['Insufficient data', 'bg-slate-500/15 text-slate-200 border-slate-400/40'],
    triage: ['Portfolio triage', 'bg-sky-500/15 text-sky-200 border-sky-400/40'],
    misstated_certificate: ['Misstated certificate', 'bg-orange-500/15 text-orange-200 border-orange-400/40'],
  }
  const [label, cls] = map[rec] || [rec, 'bg-slate-700 text-slate-200']
  return <span className={`chip border px-3 py-1 text-xs ${cls}`}>{label}</span>
}
