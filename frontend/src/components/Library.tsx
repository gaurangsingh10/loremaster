import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { coverUrl, creditText, useCovers } from '../covers'
import { IconSearch } from '../icons'

interface Ep { id: string; title: string; thread_title: string; status: string; minutes: number; chapters_done: number; total_chapters: number; updated: string }
type Filter = 'all' | 'progress' | 'done'
const PLAYABLE = new Set(['done', 'waiting_choice', 'stopped'])
const HIDDEN_KEY = 'lm-lib-hidden'

function when(iso: string) {
  const d = new Date(iso), today = new Date()
  const days = Math.floor((today.setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5)
  const t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return days === 0 ? `Today, ${t}` : days === 1 ? `Yesterday, ${t}` : days < 7 ? `${d.toLocaleDateString([], { weekday: 'long' })}` : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}
const statusLabel = (e: Ep) => e.status === 'done' ? 'Finished' : e.status === 'waiting_choice' ? 'Your choice is waiting' : e.status === 'stopped' ? 'Paused' : 'Incomplete'

export default function Library({ onOpen }: { onOpen: (id: string) => void }) {
  const covers = useCovers()
  const [eps, setEps] = useState<Ep[] | null>(null)
  const [cover, setCover] = useState<Record<string, string>>({})   // thread title -> instant story id (for its picture)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [open, setOpen] = useState<string | null>(null)
  const [hidden, setHidden] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]') } catch { return [] } })
  const [undo, setUndo] = useState<string | null>(null)
  useEffect(() => {
    api('/api/library').then(r => setEps(r.episodes)).catch(() => setEps([]))
    api('/api/instant').then(r => setCover(Object.fromEntries(r.stories.map((s: any) => [s.thread.title, s.id])))).catch(() => {})
  }, [])
  useEffect(() => { localStorage.setItem(HIDDEN_KEY, JSON.stringify(hidden)) }, [hidden])

  // One card per story thread: the most recent playable run, with earlier listens folded underneath.
  const threads = useMemo(() => {
    const by = new Map<string, Ep[]>()
    for (const e of eps ?? []) if (PLAYABLE.has(e.status) && e.chapters_done > 0) (by.get(e.thread_title) ?? by.set(e.thread_title, []).get(e.thread_title)!).push(e)
    return [...by.entries()].filter(([t]) => !hidden.includes(t)).map(([title, runs]) => ({ title, latest: runs[0], runs }))
  }, [eps, hidden])
  const needle = q.trim().toLowerCase()
  const shown = threads.filter(t => (filter === 'all' || (filter === 'done') === (t.latest.status === 'done'))
    && (!needle || `${t.title} ${t.runs.map(r => r.title).join(' ')}`.toLowerCase().includes(needle)))
  const resume = threads.find(t => t.latest.status !== 'done')
  const counts = { all: threads.length, progress: threads.filter(t => t.latest.status !== 'done').length, done: threads.filter(t => t.latest.status === 'done').length }

  const Cover = ({ title, big }: { title: string; big?: boolean }) => {
    const id = cover[title]
    return id && covers[id] ? <img className={big ? 'lib-cover big' : 'lib-cover'} src={coverUrl(id)} alt="" loading="lazy" title={creditText(covers[id])} />
      : <span className={`lib-cover blank ${big ? 'big' : ''}`} aria-hidden>{title.trim()[0]?.toUpperCase()}</span>
  }
  const Progress = ({ e }: { e: Ep }) => (
    <div className="lib-progress" role="progressbar" aria-valuemin={0} aria-valuemax={e.total_chapters} aria-valuenow={e.chapters_done} aria-label="Chapters listened">
      <span style={{ width: `${Math.min(100, 100 * e.chapters_done / Math.max(1, e.total_chapters))}%` }} /></div>)

  return (
    <div className="library">
      <h2>Lore Library</h2>
      <p className="lede">Every story you've started, one card per story. Paused stories pick up right at the choice you left.</p>
      {eps === null && <p className="muted">Loading…</p>}
      {eps !== null && threads.length === 0 && <p className="muted">No stories yet. Play an instant story to start your library.</p>}

      {resume && !needle && filter !== 'done' && (
        <button className="lib-resume" onClick={() => onOpen(resume.latest.id)}>
          <Cover title={resume.title} big />
          <div><p className="eyebrow">Continue listening</p><h3>{resume.latest.title}</h3>
            <p className="muted small">{resume.title} · chapter {resume.latest.chapters_done + 1} of {resume.latest.total_chapters} next · {when(resume.latest.updated)}</p>
            <Progress e={resume.latest} /><span className="cta">▶ Resume</span></div>
        </button>)}

      {threads.length > 0 && <div className="lib-tools">
        <label className="lib-search"><IconSearch /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search your stories" aria-label="Search your stories" /></label>
        <div className="seg small" role="group" aria-label="Filter">
          {([['all', 'All'], ['progress', 'In progress'], ['done', 'Finished']] as [Filter, string][]).map(([f, l]) => (
            <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>{l} <span className="muted">{counts[f]}</span></button>))}
        </div>
      </div>}

      <div className="lib-grid">
        {shown.map(({ title, latest, runs }) => (
          <div key={title} className="lib-card">
            <button className="lib-main" onClick={() => onOpen(latest.id)}>
              <Cover title={title} />
              <span className={`pill ${latest.status === 'done' ? 'ok' : 'warn'}`}>{statusLabel(latest)}</span>
              <h4>{latest.title}</h4>
              <p className="muted small">{title}</p>
              <Progress e={latest} />
              <small className="muted">{latest.chapters_done} of {latest.total_chapters} chapters · {latest.minutes} min · {when(latest.updated)}</small>
            </button>
            <div className="lib-foot">
              {runs.length > 1 && <button className="linkish" onClick={() => setOpen(open === title ? null : title)} aria-expanded={open === title}>
                {open === title ? 'Hide' : `${runs.length - 1} earlier listen${runs.length > 2 ? 's' : ''}`}</button>}
              <button className="linkish lib-remove" onClick={() => { setHidden(h => [...h, title]); setUndo(title) }} aria-label={`Remove ${title} from library`}>Remove</button>
            </div>
            {open === title && <ul className="lib-runs">{runs.slice(1).map(r => (
              <li key={r.id}><button className="linkish" onClick={() => onOpen(r.id)}>{r.title}</button> <span className="muted small">· {r.chapters_done}/{r.total_chapters} · {when(r.updated)}</span></li>))}</ul>}
          </div>))}
      </div>
      {threads.length > 0 && shown.length === 0 && <p className="muted">No stories match.</p>}
      {undo && <div className="toast" role="status">Removed “{undo}”. <button className="linkish" onClick={() => { setHidden(h => h.filter(x => x !== undo)); setUndo(null) }}>Undo</button>
        <button className="linkish" onClick={() => setUndo(null)} aria-label="Dismiss">×</button></div>}
      {hidden.length > 0 && !undo && <button className="linkish small" onClick={() => setHidden([])}>Show {hidden.length} removed stor{hidden.length > 1 ? 'ies' : 'y'}</button>}
    </div>
  )
}
