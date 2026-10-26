import { useEffect, useState } from 'react'
import { api, post } from '../api'
import type { Health, Mode, Thread } from '../types'
import { genreOf, scoreStory, type Prefs, type User } from '../prefs'
import { Concierge, SnapStory } from './Discover'
import { coverUrl, creditText, useCovers } from '../covers'

export interface StartOptions { instant_id?: string; thread_id?: string; topic?: string; mode: Mode; minutes: 10 | 20 | 40; skeptic?: string }
interface Instant { id: string; title: string; logline: string; thread: Thread; claims: number; grades: Record<string, number> }

const GLYPHS: Record<string, string> = {
  history: '⚖', star_wars: '✷', warhammer40k: '☩', science: '⚛', technology: '⚙', politics: '⚑',
}
const MODE_LABEL: Record<Mode, string> = { crossover: 'History behind the lore', history: 'True stories (history, science, tech, politics)', lore: 'Lore' }
const UNIVERSE = (t: Thread) => t.packs.includes('star_wars') ? 'Star Wars' : t.packs.includes('warhammer40k') ? 'Warhammer 40K' : 'History'
const GENRE_LABEL: Record<string, string> = { history: 'History', science: 'Science', technology: 'Technology', politics: 'Politics & ideas' }
const TAG = (t: Thread) => t.mode === 'crossover' ? `History × ${UNIVERSE(t)}` : t.mode === 'lore' ? `Lore · ${UNIVERSE(t)}` : GENRE_LABEL[genreOf(t)] ?? 'History'
type Filter = 'all' | 'crossover' | 'history' | 'science' | 'technology' | 'politics' | 'lore'
const FILTERS: [Filter, string][] = [['all', 'All'], ['crossover', 'History × lore'], ['history', 'History'], ['science', 'Science'], ['technology', 'Technology'], ['politics', 'Politics'], ['lore', 'Lore']]
const matches = (t: Thread, f: Filter) => f === 'all' ? true : f === 'crossover' ? t.mode === 'crossover' : f === 'lore' ? t.mode === 'lore' : t.mode !== 'crossover' && genreOf(t) === f

function Emblem({ thread }: { thread: Thread }) {
  const glyph = GLYPHS[thread.packs.find(p => p !== 'history') ?? 'history'] ?? GLYPHS[genreOf(thread)] ?? '✦'
  return (
    <div className="emblem" aria-hidden>
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="56" fill="rgba(212,166,74,.16)" />
        <circle cx="60" cy="60" r="44" fill="none" stroke="#a8771f" strokeWidth="1.2" strokeDasharray="2 4" />
        <circle cx="60" cy="60" r="34" fill="none" stroke="#a8771f" strokeWidth="1.5" />
      </svg>
      <span className="glyph">{glyph}</span>
    </div>
  )
}

export default function Home({ health, onStart, starting, error, onOpen, prefs, user, onQuiz }: {
  health: Health | null; onStart: (o: StartOptions) => void; starting: boolean; error: string; onOpen: (id: string) => void
  prefs: Prefs; user: User | null; onQuiz: () => void
}) {
  const covers = useCovers()
  const [instant, setInstant] = useState<Instant[]>([])
  const [threads, setThreads] = useState<Thread[]>([])
  const [surprise, setSurprise] = useState<Thread[]>([])
  const [mode, setMode] = useState<Mode>('crossover')
  const [minutes, setMinutes] = useState<10 | 20 | 40>(prefs.minutes ?? 10)
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState('')
  const [resume, setResume] = useState<any | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    api('/api/instant').then(r => setInstant(r.stories)).catch(() => {})
    api('/api/menu').then(r => setThreads(r.threads)).catch(() => {})
    api('/api/library').then(r => setResume(r.episodes.find((e: any) => e.status === 'waiting_choice' && e.chapters_done > 0) ?? null)).catch(() => {})
  }, [])

  async function doSurprise() {
    setBusy('The Showrunner is dreaming up threads…')
    try { setSurprise((await post(`/api/menu/surprise?mode=${mode}`)).threads) } catch (e: any) { setBusy(e.message); return }
    setBusy('')
  }

  const demo = health?.demo_only
  const personalized = prefs.onboarded && (prefs.worlds.length > 0 || prefs.interests.length > 0)
  const shownInstant = instant.filter(s => matches(s.thread, filter))
    .map((s, i) => ({ s, i, score: personalized ? scoreStory(s.thread, prefs) : 0 }))
    .sort((a, b) => b.score - a.score || a.i - b.i)
  const topPick = personalized ? shownInstant[0]?.s.id : undefined

  return (
    <div className="home">
      <section className="hero">
        <p className="eyebrow">True stories & deep lore for the long commute</p>
        {user && <p className="welcome">Welcome back, {user.name.split(' ')[0]}{prefs.persona ? ` · ${prefs.persona}` : ''}</p>}
        <h2>History, legend, <span className="gold">and the line between them.</span></h2>
        <p className="lede">History, science, technology, politics, and the lore of Star Wars and Warhammer 40K. Press play on a story. Choose where it goes at every chapter. Tap any claim to see whether it's
          {' '}<b className="g-doc">documented</b>, <b className="g-deb">debated</b>, <b className="g-leg">legend</b> or <b className="h-fan">fan theory</b>, with the source.</p>
      </section>

      {resume && (
        <button className="resume" onClick={() => onOpen(resume.id)}>
          <span className="resume-icon" aria-hidden>▶</span>
          <span><small>Continue where you left off</small><b>{resume.title}</b><em>Chapter {resume.chapters_done} of {resume.total_chapters} · a choice is waiting</em></span>
        </button>
      )}

      <div className="discover">
        <Concierge onStart={onStart} disabled={!!demo} />
        <SnapStory onStart={onStart} disabled={!!demo} />
      </div>

      {instant.length > 0 && (
        <section className="instant">
          <div className="section-head">
            <h3>⚡ Instant stories <span className="muted">· {personalized ? `sorted for ${prefs.persona || 'you'}` : 'start in one second, every branch ready'}</span>
              {!prefs.onboarded || !personalized ? <button className="linkish" onClick={onQuiz}>personalize (15 s)</button> : null}</h3>
            <div className="seg small" role="group" aria-label="Filter stories">
              {FILTERS.map(([f, label]) => (
                <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>{label}</button>))}
            </div>
          </div>
          <div className="threads">
            {shownInstant.map(({ s, score }) => (
              <button key={s.id} className={`thread ${personalized && score > 0 ? 'picked' : ''}`} disabled={starting} onClick={() => onStart({ instant_id: s.id, mode: s.thread.mode, minutes: 10 })}>
                {covers[s.id] && <img className="thread-cover" src={coverUrl(s.id)} alt="" loading="lazy" title={creditText(covers[s.id])} />}
                {personalized && score > 0 && <span className="for-you">{s.id === topPick ? '★ Top pick for you' : 'For you'}</span>}
                <div className="thread-top"><Emblem thread={s.thread} /><span className="tag">{TAG(s.thread)}</span></div>
                <h3>{s.thread.title}</h3>
                <p>{s.thread.hook}</p>
                <span className="cta">▶ Play now · 10 min</span>
              </button>))}
          </div>
        </section>
      )}

      <section className="create">
        <h3>✦ Make a new episode <span className="muted">· written live by six agents in about 30 seconds</span></h3>
        <div className="controls">
          <div className="seg" role="group" aria-label="Length">
            {([10, 20, 40] as const).map(n => (
              <button key={n} className={minutes === n ? 'on' : ''} onClick={() => setMinutes(n)}>{n} min</button>))}
          </div>
          <div className="seg" role="group" aria-label="Mode for your own topic">
            {(['crossover', 'history', 'lore'] as Mode[]).map(m => (
              <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{MODE_LABEL[m]}</button>))}
          </div>
        </div>
        <form className="ask" onSubmit={e => { e.preventDefault(); if (topic.trim()) onStart({ topic: topic.trim(), mode, minutes }) }}>
          <input value={topic} maxLength={300} onChange={e => setTopic(e.target.value)} disabled={!!demo} aria-label="Ask about anything"
            placeholder={demo ? 'Ask about anything (needs an API key)' : 'Ask about anything: "Why did Byzantium last 1,000 years?", "How do vaccines work?", "Where did the Electoral College come from?"'} />
          <button disabled={starting || !topic.trim() || !!demo}>{starting ? 'Summoning…' : 'Tell me'}</button>
        </form>
        {error && <p className="error">{error}</p>}
        <div className="threads compact">
          {[...threads, ...surprise].map(t => (
            <button key={t.id} className={`thread small ${t.curated ? '' : 'fresh'}`} disabled={starting || !!demo}
              onClick={() => onStart({ thread_id: t.curated ? t.id : undefined, topic: t.curated ? undefined : `${t.title}: ${t.hook}`, mode: t.mode, minutes })}>
              <span className="tag">{TAG(t)}</span>
              <h3>{t.title}</h3>
              <span className="cta">✦ Write it live · {minutes} min</span>
            </button>))}
          <button className="thread small surprise" disabled={starting || !!demo || !!busy} onClick={doSurprise}>
            <span className="tag">Showrunner's pick</span>
            <h3>Surprise me</h3>
            <span className="cta">{busy || 'Two threads you didn’t know you wanted'}</span>
          </button>
        </div>
      </section>
    </div>
  )
}
