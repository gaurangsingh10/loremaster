import { useEffect, useMemo, useRef, useState } from 'react'
import { AGENTS, API, GRADE_INFO, api, fmtUsd, post } from '../api'
import { ChapterPlayer, fmtTime, type PlayerState } from '../audioPlayer'
import type { AgentActivity, Chapter, Episode, GradedClaim, Health, ReadingItem, Spend } from '../types'
import { localPrefs, voiceId, type Prefs } from '../prefs'
import { IconBack15, IconFwd15, IconNext, IconPause, IconPlay, IconPrev } from '../icons'
import { stopSample } from '../sample'
import { logEvent } from '../events'
import { AskPanel, CallItCard, MythOrFact } from './Interactive'
import type { CallIt } from '../types'

type Feed = { ts: number; text: string; kind: string }
const FACT = ['Documented', 'Canon']
const AUTO_SECONDS = 15

export default function Player({ episodeId, health, prefs, onFeedback, onNew }: {
  episodeId: string; health: Health | null; prefs: Prefs; onFeedback: () => void; onNew: () => void
}) {
  const [ep, setEp] = useState<Partial<Episode>>({ chapters: [] })
  const [plan, setPlan] = useState<{ title: string; logline: string; chapters: string[]; instant?: boolean } | null>(null)
  const [activity, setActivity] = useState<Record<string, AgentActivity>>({})
  const [spend, setSpend] = useState<Spend | null>(null)
  const [feed, setFeed] = useState<Feed[]>([])
  const [status, setStatus] = useState<string>('running')
  const [message, setMessage] = useState('')
  const [options, setOptions] = useState<string[]>([])
  const [reading, setReading] = useState<ReadingItem[]>([])
  const [current, setCurrent] = useState(0)
  const [drawer, setDrawer] = useState<{ claim: GradedClaim; from: HTMLElement | null } | null>(null)
  const [working, setWorking] = useState<string>('The Showrunner is planning your episode…')
  const [choosing, setChoosing] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([])
  const [voice, setVoice] = useState(voiceId(prefs))
  const [ps, setPs] = useState<PlayerState>({ playing: false, loading: false, segment: 0, total: 0, engine: '', error: '', ended: false, position: 0, duration: 0, marks: [] })
  const [rate, setRate] = useState(prefs.speed || 1)
  const [tip, setTip] = useState(localStorage.getItem('lm-tip') !== 'seen')
  const [filter, setFilter] = useState<string | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)
  const [atEnd, setAtEnd] = useState(false)          // reader scrolled to the end of the chapter
  const [choiceOpen, setChoiceOpen] = useState(false) // listener opened the choices manually
  const endRef = useRef<HTMLDivElement>(null)
  const [askOpen, setAskOpen] = useState(false)
  const [callDone, setCallDone] = useState<Record<number, boolean>>({})
  const resumeAfter = useRef(false)
  const [t0] = useState(Date.now())
  const [elapsed, setElapsed] = useState(0)
  const player = useRef(new ChapterPlayer())
  const autoplayNext = useRef(false)

  const chapters = ep.chapters ?? []
  const chapter: Chapter | undefined = chapters[current]
  const total = ep.total_chapters ?? 0
  const isLast = !!chapter && chapter.index === chapters[chapters.length - 1]?.index
  const canChoose = isLast && (status === 'waiting_choice' || status === 'stopped') && chapters.length < total
  const busy = (status === 'running' || choosing) && !stopping

  // ---------------------------------------------------------------- live events (SSE)
  useEffect(() => {
    let es: EventSource | null = null
    let closed = false
    const log = (text: string, kind = 'info') => setFeed(f => [{ ts: Date.now(), text, kind }, ...f].slice(0, 60))
    api<Episode>(`/api/episode/${episodeId}`).then(e => {
      setEp(e); if (e.title) setPlan(p => ({ title: e.title, logline: e.logline, chapters: p?.chapters ?? [] }))
      if (e.reading?.length) setReading(e.reading)
      setStatus(e.status)
      if (e.chapters.length) { setCurrent(e.chapters.length - 1); setOptions(e.chapters[e.chapters.length - 1].branch_options) }
    }).catch(() => {})
    api('/api/voices').then(v => setVoices(v.voices)).catch(() => {})
    es = new EventSource(`${API}/api/episode/${episodeId}/stream`)
    es.onmessage = msg => {
      const ev = JSON.parse(msg.data)
      switch (ev.type) {
        case 'plan': setPlan({ title: ev.title, logline: ev.logline, chapters: (ev.chapters ?? []).map((c: any) => c.title), instant: ev.instant }); log(`Showrunner planned "${ev.title}"`, 'plan'); break
        case 'agent_started':
          setActivity(a => ({ ...a, [ev.agent]: { agent: ev.agent, state: 'working', label: ev.label } }))
          setWorking(`${cap(ev.agent)}: ${ev.label}`); log(`${cap(ev.agent)} started · ${ev.label}`, ev.agent); break
        case 'agent_done':
          setActivity(a => ({ ...a, [ev.agent]: { agent: ev.agent, state: 'done', label: ev.label, seconds: ev.seconds, cost: ev.usage?.cost_usd } }))
          log(`${cap(ev.agent)} done in ${ev.seconds}s · ${fmtUsd(ev.usage?.cost_usd ?? 0)}`, ev.agent); break
        case 'agent_retry': setWorking(`${cap(ev.agent)} hit a temporary server hiccup, retrying (try ${ev.attempt} of 3)…`); log(`${cap(ev.agent)}: ${ev.error}, retrying in ${ev.delay}s`, 'bad'); break
        case 'agent_error': setActivity(a => ({ ...a, [ev.agent]: { agent: ev.agent, state: 'error', label: ev.error } })); log(`${cap(ev.agent)} error: ${ev.error}`, 'bad'); break
        case 'tool_call':
          setActivity(a => ({ ...a, [ev.agent]: { ...(a[ev.agent] ?? { agent: ev.agent, state: 'working', label: '' }), lastTool: `${ev.tool}(${ev.args})` } }))
          setWorking(`Researcher is reading: ${ev.args}`)
          log(`↳ ${ev.tool}(${ev.args}) → ${ev.result}`, 'tool'); break
        case 'guard': log(`Guardian (${ev.layer}): ${ev.verdict.allowed ? 'allowed' : 'refused'}: ${ev.verdict.reason}`, ev.verdict.allowed ? 'guardian' : 'bad'); break
        case 'spend': setSpend(ev); break
        case 'chapter_started': setWorking(`Writing chapter ${ev.chapter}: ${ev.title}`); break
        case 'evidence': log(`Researcher kept ${ev.cards.length} evidence cards`, 'researcher'); break
        case 'draft_ready': if (ev.unsupported_by_code) log(`Tripwire: ${ev.unsupported_by_code} claim(s) cite no real evidence → Skeptic`, 'bad'); break
        case 'chapter_ready':
          setEp(e => {
            const list = [...(e.chapters ?? []).filter(c => c.index !== ev.chapter.index), ev.chapter].sort((a, b) => a.index - b.index)
            return { ...e, chapters: list }
          })
          setOptions(ev.chapter.branch_options); setWorking(''); setChoosing(false)
          if (autoplayNext.current) setCurrent(ev.chapter.index - 1)
          log(`Chapter ${ev.chapter.index} ready: ${ev.chapter.claims.length} claims graded`, 'ok'); break
        case 'waiting_choice': setStatus('waiting_choice'); setChoosing(false); break
        case 'games_ready':
          setEp(e => ({ ...e, chapters: (e.chapters ?? []).map(c => c.index === ev.chapter ? { ...c, games: ev.games } : c) }))
          log(`Quizmaster: Myth or Fact? and Call it ready for chapter ${ev.chapter}`, 'ok'); break
        case 'answer': log(`Answerer replied: “${String(ev.question).slice(0, 40)}”`, 'ok'); break
        case 'choice': log(`You chose: ${ev.branch}`, 'plan'); break
        case 'final': setStatus('done'); setReading(ev.reading ?? []); setWorking(''); setChoosing(false); break
        case 'stopped': setStatus('stopped'); setStopping(false); setChoosing(false); setWorking(''); setMessage('Stopped. Nothing more will be spent.'); break
        case 'budget_stop': setStatus('budget_stop'); setMessage(`Budget cap reached: ${ev.reason}`); setWorking(''); break
        case 'refused': setStatus('refused'); setMessage(`${ev.verdict.reason}${ev.verdict.safe_reframe ? ` Try instead: “${ev.verdict.safe_reframe}”` : ''}`); setWorking(''); break
        case 'error': setStatus('error'); setMessage(ev.message); setWorking(''); setChoosing(false); break
        case 'episode':
          setEp(prev => sameChapters(prev.chapters, ev.episode.chapters) ? { ...ev.episode, chapters: prev.chapters } : ev.episode)
          setStatus(ev.episode.status)
          if (ev.episode.reading?.length) setReading(ev.episode.reading)
          break
      }
    }
    es.onerror = () => { if (!closed) es?.close() }
    const p = player.current
    return () => { closed = true; es?.close(); p.stop() }
  }, [episodeId])

  // elapsed timer while waiting
  useEffect(() => {
    if (!busy) return
    const iv = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000)
    return () => clearInterval(iv)
  }, [busy, t0])

  // ---------------------------------------------------------------- audio: (re)load when the chapter TEXT changes
  useEffect(() => { player.current.onChange = setPs; player.current.setRate(prefs.speed || 1) }, [prefs.speed])
  useEffect(() => { setVoice(voiceId(prefs)) }, [prefs])
  const chapterKey = chapter ? `${chapter.index}:${chapter.narration.length}` : ''
  useEffect(() => {
    if (!chapter) return
    const p = player.current
    const auto = autoplayNext.current
    p.load(episodeId, chapter.index, chapter.narration, voice).then(() => {
      const saved = Number(localStorage.getItem(`lm-pos-${episodeId}-${chapter.index}`) || 0)
      if (saved > 5 && !auto) p.seekTo(saved)              // resume where you left off
      if (auto) { autoplayNext.current = false; p.play() }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterKey, voice, episodeId])

  // remember playback position per chapter (every ~5 s of progress)
  useEffect(() => {
    if (!chapter || !ps.duration) return
    const key = `lm-pos-${episodeId}-${chapter.index}`
    if (ps.ended) localStorage.removeItem(key)
    else if (ps.position > 5 && Math.floor(ps.position) % 5 === 0) localStorage.setItem(key, String(Math.floor(ps.position)))
  }, [ps.position, ps.ended, ps.duration, chapter, episodeId])

  // keyboard shortcuts: Space play/pause, ←/→ 15 s, Shift+←/→ previous/next section
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (drawer || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable) return
      const p = player.current
      if (e.key === ' ' && t.tagName !== 'BUTTON') { e.preventDefault(); setCountdown(null); p.toggle() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); e.shiftKey ? p.skip(1) : p.skipSeconds(15) }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? p.skip(-1) : p.skipSeconds(-15) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawer])

  // Media Session: lock-screen / headphone controls
  useEffect(() => {
    if (!('mediaSession' in navigator) || !chapter) return
    navigator.mediaSession.metadata = new MediaMetadata({ title: `Ch. ${chapter.index}: ${chapter.title}`, artist: 'Loremaster', album: plan?.title ?? '' })
    const p = player.current
    navigator.mediaSession.setActionHandler('play', () => p.play())
    navigator.mediaSession.setActionHandler('pause', () => p.pause())
    navigator.mediaSession.setActionHandler('nexttrack', () => p.skip(1))
    navigator.mediaSession.setActionHandler('previoustrack', () => p.skip(-1))
    navigator.mediaSession.setActionHandler('seekforward', () => p.skipSeconds(15))
    navigator.mediaSession.setActionHandler('seekbackward', () => p.skipSeconds(-15))
    try { navigator.mediaSession.setActionHandler('seekto', d => { if (d.seekTime !== undefined) p.seekTo(d.seekTime) }) } catch { /* older browsers */ }
  }, [chapter, plan?.title])

  // show the full choice bar only at the end of the chapter (scrolled there, or audio finished)
  useEffect(() => {
    const el = endRef.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setAtEnd(e.isIntersecting), { rootMargin: '0px 0px -120px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [chapterKey])
  useEffect(() => { setChoiceOpen(false) }, [chapterKey])

  // auto-continue countdown after the last chapter finishes playing
  useEffect(() => {
    if (ps.ended && canChoose && options.length) setCountdown(AUTO_SECONDS)
  }, [ps.ended, canChoose, options.length])
  useEffect(() => {
    if (countdown === null) return
    if (countdown <= 0) { setCountdown(null); choose(options[0]); return }
    const t = setTimeout(() => setCountdown(c => (c === null ? null : c - 1)), 1000)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countdown])

  async function choose(branch: string) {
    setCountdown(null); setMessage('')
    logEvent('branch_choice', episodeId, chapter?.index ?? null, { branch: branch.slice(0, 120) })
    setChoosing(true); setWorking('The Showrunner is reshaping the story around your choice…'); autoplayNext.current = localPrefs().autoplay_next
    try {
      await post(`/api/episode/${episodeId}/choose`, { branch })
      if (episodeId === 'demo') {
        const e = await api<Episode>(`/api/episode/demo`)
        const next = e.chapters[chapters.length]
        if (next) { setEp(p => ({ ...p, chapters: [...chapters, next] })); setCurrent(chapters.length); setOptions(next.branch_options) }
        if (chapters.length + 1 >= e.chapters.length) { setStatus('done'); setReading(e.reading) }
        setChoosing(false); setWorking('')
      }
    } catch (e: any) { setMessage(e.message); setChoosing(false) }
  }

  async function stop() {
    setStopping(true)
    try { await post(`/api/episode/${episodeId}/cancel`) } catch { /* ignore */ }
    setTimeout(() => { setStopping(false); setChoosing(false); setStatus(s => (s === 'running' ? 'stopped' : s)); setWorking('') }, 1500)
  }

  function openClaim(claim: GradedClaim, el: HTMLElement | null) {
    setDrawer({ claim, from: el })
    logEvent('claim_open', episodeId, chapter?.index ?? null, { grade: claim.grade })
    if (tip) { setTip(false); localStorage.setItem('lm-tip', 'seen') }
  }

  const activeParas = useMemo(() => (ps.playing || ps.segment > 0 ? player.current.paraIndices(ps.segment) : []), [ps.segment, ps.playing])

  // Call it: pause the narrator right before the reveal paragraph until the listener makes a call
  const activeCall: CallIt | null = chapter?.games?.call_it && !callDone[chapter.index] ? chapter.games.call_it : null
  useEffect(() => {
    if (!activeCall || !ps.playing) return
    const paras = player.current.paraIndices(ps.segment)
    if (paras.some(i => i >= activeCall.reveal_para)) {
      player.current.pause(); resumeAfter.current = true
      document.getElementById('callit-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [ps.segment, ps.playing, activeCall])
  function callAnswered() {
    if (!chapter) return
    setCallDone(d => ({ ...d, [chapter.index]: true }))
    if (resumeAfter.current) { resumeAfter.current = false; player.current.play() }
  }
  // listening time (impact metric), in 30 s ticks
  useEffect(() => {
    if (!ps.playing) return
    const iv = setInterval(() => logEvent('listen_seconds', episodeId, chapter?.index ?? null, { seconds: 30 }), 30000)
    return () => clearInterval(iv)
  }, [ps.playing, episodeId, chapter?.index])

  // follow along: keep the paragraph being read on screen (only if it has scrolled out of view)
  useEffect(() => {
    if (!ps.playing || !activeParas.length) return
    const el = document.getElementById(`para-${activeParas[0]}`)
    if (!el) return
    const r = el.getBoundingClientRect()
    const bottomLimit = window.innerHeight - 190   // stay clear of the docked player
    if (r.top < 70 || r.top > bottomLimit) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeParas, ps.playing])

  return (
    <div className="player">
      <section className="ep-head">
        <p className="eyebrow">{ep.thread?.title ?? 'Episode'}{plan?.instant || episodeId.startsWith('i') ? ' · ⚡ instant story' : ''}{ep.demo ? ' · sample episode' : ''}</p>
        <h2>{plan?.title ?? 'Summoning your episode…'}</h2>
        {plan?.logline && <p className="lede">{plan.logline}</p>}
        <div className="chapter-nav" aria-label="Chapters">
          {Array.from({ length: total || 1 }).map((_, i) => (
            <button key={i} className={`dot ${i === current ? 'on' : ''} ${i < chapters.length ? 'ready' : ''}`} disabled={i >= chapters.length}
              aria-label={`Chapter ${i + 1}${chapters[i] ? `: ${chapters[i].title}` : ' (not written yet)'}`}
              onClick={() => { player.current.pause(); setCurrent(i) }}>{i + 1}</button>))}
          {chapter && <span className="chapter-of">Chapter {chapter.index} of {total} · {chapter.title}</span>}
        </div>
      </section>

      <div className="player-grid">
        <section className="stage">
          {message && <div className={`banner ${['refused', 'error'].includes(status) ? 'bad' : 'warn'}`} role="status">{message}
            {status === 'stopped' && !chapters.length && <button className="ghost small-btn" onClick={onNew}>Pick another thread</button>}</div>}

          {!chapter && busy && <Waiting text={working} elapsed={elapsed} planTitles={plan?.chapters ?? []} onStop={stop} stopping={stopping} onInstant={onNew} />}

          {chapter && (
            <article className="manuscript">
              {tip && chapter.claims.length > 0 && (
                <div className="tip" role="note">
                  <b>Is that true?</b> Tap any mark like <span className="chip g-fact sample">D</span> <span className="chip g-debated sample">≈</span> <span className="chip g-legend sample">L</span> after a sentence to see how solid that claim is, and the source.
                  <button className="tip-x" aria-label="Dismiss tip" onClick={() => { setTip(false); localStorage.setItem('lm-tip', 'seen') }}>Got it</button>
                </div>)}
              <h3 className="chapter-title"><span>Chapter {chapter.index}</span>{chapter.title}{chapter.revised && <em className="revised" title="The Skeptic sent this chapter back once to fix or flag claims">revised by Skeptic</em>}</h3>
              <Narration chapter={chapter} activeParas={activeParas} onClaim={openClaim} onPara={i => player.current.seekToPara(i)}
                callIt={activeCall} callSlot={activeCall ? <div id="callit-card"><CallItCard call={activeCall} episodeId={episodeId} chapter={chapter.index} onAnswered={callAnswered} /></div> : null} />
              <GradeTally claims={chapter.claims} filter={filter} setFilter={setFilter} onClaim={openClaim} />
              {chapter.games?.myth_or_fact?.length ? <MythOrFact key={chapter.index} items={chapter.games.myth_or_fact} episodeId={episodeId} chapter={chapter.index} /> : null}
              <div ref={endRef} aria-hidden style={{ height: 1 }} />
              {!isLast && <button className="ghost next-ch" onClick={() => { player.current.pause(); setCurrent(current + 1) }}>Next chapter →</button>}
            </article>
          )}

          {chapter && isLast && busy && <Waiting text={working} elapsed={0} planTitles={[]} onStop={stop} stopping={stopping} small />}

          {status === 'done' && isLast && (
            <div className="finale">
              <p className="eyebrow">The end of this thread</p>
              {chapter && <p className="serif">Where it could go next: {chapter.branch_options.join(' · ')}</p>}
              {reading.length > 0 && <><h4>Further reading</h4><ul className="reading">{reading.map(r => (
                <li key={r.title}><a href={r.url} target="_blank" rel="noreferrer"><b>{r.title}</b></a> · {r.author}{r.year ? ` (${r.year})` : ''}<br /><span>{r.why}</span></li>))}</ul></>}
              <div className="row"><button onClick={onFeedback}>Rate this episode</button><button className="ghost" onClick={onNew}>Pick another story</button></div>
            </div>
          )}
        </section>

        <aside className="side">
          <details className="card behind" open={typeof window !== 'undefined' && window.innerWidth > 960}>
            <summary><span>Behind the scenes</span><small>{busy ? 'agents working…' : `${fmtUsd(spend?.total_usd ?? ep.total_usd ?? 0)} so far`}</small></summary>
            <AgentPanel activity={activity} />
            <SpendMeter spend={spend} episode={ep} budget={health?.budget_usd ?? 0.05} />
            <div className="feed">
              <h4>Live log</h4>
              <ul>{feed.map((f, i) => <li key={i} className={f.kind}>{f.text}</li>)}</ul>
              {!feed.length && <p className="muted small">{plan?.instant || episodeId.startsWith('i') ? 'Instant story: written ahead of time by the same six agents.' : 'Agent activity appears here.'}</p>}
            </div>
          </details>
        </aside>
      </div>

      {/* sticky bottom: the choice bar (when it's time) above the mini-player */}
      <div className="dock">
        {canChoose && !busy && !(atEnd || ps.ended || choiceOpen || status === 'stopped') && (
          <button className="choice-pill" onClick={() => setChoiceOpen(true)}>↑ {options.length} paths ready for chapter {(chapter?.index ?? 0) + 1}: choose when you're ready</button>
        )}
        {canChoose && !busy && (atEnd || ps.ended || choiceOpen || status === 'stopped') && (
          <div className="choice" role="region" aria-label="Choose the next chapter">
            <p className="eyebrow">{status === 'stopped' ? 'Pick a path to continue' : `Chapter ${chapter?.index} complete. You decide what happens next`}
              {countdown !== null && <span className="countdown"> · continuing with the first path in {countdown}s <button className="linkish" onClick={() => setCountdown(null)}>wait</button></span>}</p>
            <div className="choice-row">
              {options.map(o => <button key={o} disabled={choosing} onClick={() => choose(o)}>{o}</button>)}
            </div>
          </div>
        )}
        {chapter && (
          <div className="mini" role="region" aria-label="Audio player">
            <Scrubber ps={ps} chapter={chapter} player={player.current} />
            <div className="mini-row">
              <button className="play" onClick={() => { setCountdown(null); stopSample(); player.current.toggle() }} aria-label={ps.playing ? 'Pause narration' : 'Play narration'}>
                {ps.loading && ps.playing ? <span className="spin" aria-hidden>◌</span> : ps.playing ? <IconPause /> : <IconPlay />}</button>
              <div className="mini-info">
                <b>{chapter.title}</b>
                <small aria-live="polite" title="Shortcuts: Space play/pause · ←/→ 15 s · Shift+←/→ section">{ps.total ? `Section ${Math.min(ps.segment + 1, ps.total)} of ${ps.total}` : 'Preparing audio…'}
                  {ps.engine && <> · {ps.engine === 'kokoro' ? 'neural voice' : ps.engine === 'browser' ? 'browser voice' : ps.engine === 'macos' ? 'Mac voice' : ps.engine}</>}
                  {ps.error && <span className="err"> · {ps.error}</span>}</small>
              </div>
              <button className="ask-btn" onClick={() => setAskOpen(true)} aria-label="Ask the narrator a question" title="Ask the narrator">💬 Ask</button>
              <div className="mini-buttons">
                <button onClick={() => player.current.skip(-1)} aria-label="Previous section" title="Previous section" className="opt"><IconPrev /></button>
                <button onClick={() => player.current.skipSeconds(-15)} aria-label="Back 15 seconds" title="Back 15 seconds"><IconBack15 /></button>
                <button onClick={() => player.current.skipSeconds(15)} aria-label="Forward 15 seconds" title="Forward 15 seconds"><IconFwd15 /></button>
                <button onClick={() => player.current.skip(1)} aria-label="Next section" title="Next section"><IconNext /></button>
              </div>
              <select value={rate} aria-label="Playback speed" onChange={e => { const r = Number(e.target.value); setRate(r); player.current.setRate(r) }}>
                {[...new Set([0.8, 0.9, 1, 1.1, 1.25, 1.5, rate])].sort().map(r => <option key={r} value={r}>{r}×</option>)}
              </select>
              {voices.length > 0 && (
                <select value={voice} aria-label="Narrator voice" onChange={e => { setVoice(e.target.value); localStorage.setItem('lm-voice', e.target.value) }}>
                  {voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>)}
            </div>
          </div>
        )}
      </div>
      {askOpen && chapter && <AskPanel episodeId={episodeId} chapter={chapter.index} voice={voice}
        onClose={() => setAskOpen(false)}
        onPauseStory={() => { resumeAfter.current = player.current.state.playing; player.current.pause() }}
        onResumeStory={() => { player.current.play() }} />}
      {drawer && <ClaimDrawer claim={drawer.claim} onClose={() => { const el = drawer.from; setDrawer(null); el?.focus() }} />}
    </div>
  )
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

function Scrubber({ ps, chapter, player }: { ps: PlayerState; chapter: Chapter; player: ChapterPlayer }) {
  const [drag, setDrag] = useState<number | null>(null)
  const paras = useMemo(() => chapter.narration.split(/\n+/).filter(p => p.trim()).map(p => p.replace(/\s*\[c\d+\]/g, '').trim()), [chapter.narration])
  const dur = Math.max(ps.duration, 1)
  const pos = drag ?? ps.position
  const commit = () => { if (drag !== null) { player.seekTo(drag); setDrag(null) } }
  const label = (i: number) => { const p = player.paraIndices(i)[0]; return p !== undefined && paras[p] ? paras[p].split(' ').slice(0, 7).join(' ') + '…' : `Section ${i + 1}` }
  return (
    <div className="scrubber">
      <span className="time">{fmtTime(pos)}</span>
      <div className="track-wrap">
        <div className="track"><i style={{ width: `${(pos / dur) * 100}%` }} /></div>
        {ps.marks.slice(1).map((m, k) => (
          <button key={k} className={`mark ${k + 1 <= ps.segment ? 'past' : ''}`} style={{ left: `${(m / dur) * 100}%` }}
            title={`Section ${k + 2}: ${label(k + 1)}`} aria-label={`Jump to section ${k + 2}: ${label(k + 1)}`}
            onClick={() => player.seekTo(m + 0.01)} />))}
        <input type="range" min={0} max={dur} step={0.5} value={Math.min(pos, dur)} aria-label="Seek in chapter"
          aria-valuetext={`${fmtTime(pos)} of ${fmtTime(ps.duration)}`}
          onChange={e => setDrag(Number(e.target.value))} onPointerUp={commit} onTouchEnd={commit} onKeyUp={commit} onBlur={commit} />
      </div>
      <span className="time">{ps.duration ? fmtTime(ps.duration) : '--:--'}</span>
    </div>
  )
}
function sameChapters(a?: Chapter[], b?: Chapter[]) {
  return !!a && !!b && a.length === b.length && a.every((c, i) => c.index === b[i].index && c.narration === b[i].narration)
}

export const GRADE_CLASS: Record<string, { cls: string; mark: string }> = {
  Documented: { cls: 'g-fact', mark: 'D' }, Canon: { cls: 'g-fact', mark: 'C' },
  Debated: { cls: 'g-debated', mark: '≈' }, Conflicting: { cls: 'g-debated', mark: '≠' },
  Legend: { cls: 'g-legend', mark: 'L' }, Legends: { cls: 'g-legend', mark: 'L' },
  'Fan theory': { cls: 'g-fan', mark: 'F' }, Interpretation: { cls: 'g-interp', mark: 'i' },
  Unsupported: { cls: 'g-bad', mark: '?' },
}

function Waiting({ text, elapsed, planTitles, onStop, stopping, onInstant, small }: {
  text: string; elapsed: number; planTitles: string[]; onStop: () => void; stopping: boolean; onInstant?: () => void; small?: boolean
}) {
  return (
    <div className={`waiting ${small ? 'small' : ''}`} aria-live="polite">
      <div className="quill" aria-hidden>❦</div>
      <div className="waiting-body">
        <p className="waiting-text">{text || 'Working…'}</p>
        {!small && <p className="muted small">New episodes take about 30 seconds: six agents research, write and fact-check chapter 1.{elapsed ? ` (${elapsed}s)` : ''}</p>}
        {!small && planTitles.length > 0 && <ol className="skeleton">{planTitles.map((t, i) => <li key={i} className={i === 0 ? 'now' : ''}>{t}</li>)}</ol>}
        {!small && <div className="skeleton-lines" aria-hidden><i /><i /><i /><i /></div>}
        <div className="row">
          <button className="stop" onClick={onStop} disabled={stopping}>{stopping ? 'Stopping…' : '■ Stop writing'}</button>
          {onInstant && <button className="linkish" onClick={onInstant}>or play an instant story with no wait →</button>}
        </div>
      </div>
    </div>
  )
}

function Narration({ chapter, activeParas, onClaim, onPara, callIt, callSlot }: {
  chapter: Chapter; activeParas: number[]; onClaim: (c: GradedClaim, el: HTMLElement) => void; onPara: (i: number) => void
  callIt?: CallIt | null; callSlot?: React.ReactNode
}) {
  const byId = Object.fromEntries(chapter.claims.map(c => [c.id, c]))
  const paras = chapter.narration.split(/\n+/).filter(p => p.trim())
  return (
    <div className="narration">
      {paras.map((p, pi) => {
        const parts = p.split(/(\s*\[c\d+\])/g)
        const veiled = !!callIt && pi >= callIt.reveal_para
        return (
          <div key={pi} style={{ display: 'contents' }}>
          {callIt && pi === callIt.reveal_para && callSlot}
          <p id={`para-${pi}`} aria-hidden={veiled || undefined} className={`${pi === 0 ? 'dropcap' : ''} ${activeParas.includes(pi) ? 'speaking' : ''} ${veiled ? 'veiled' : ''}`} onDoubleClick={() => onPara(pi)} title="Double-click to play from here">
            {parts.map((s, si) => {
              const m = s.match(/\[(c\d+)\]/)
              if (!m) return <span key={si}>{s}</span>
              const c = byId[m[1]]
              if (!c) return null
              const g = GRADE_CLASS[c.grade] ?? { cls: 'g-interp', mark: '•' }
              return <button key={si} className={`chip ${g.cls}`} aria-label={`${c.grade}: ${c.text}. Show evidence`} title={`${c.grade}: is that true?`}
                onClick={e => onClaim(c, e.currentTarget)}>{g.mark}</button>
            })}
          </p>
          </div>
        )
      })}
    </div>
  )
}

function GradeTally({ claims, filter, setFilter, onClaim }: { claims: GradedClaim[]; filter: string | null; setFilter: (g: string | null) => void; onClaim: (c: GradedClaim, el: HTMLElement) => void }) {
  const counts: Record<string, number> = {}
  claims.forEach(c => { counts[c.grade] = (counts[c.grade] ?? 0) + 1 })
  const list = claims.filter(c => (filter ? c.grade === filter : !FACT.includes(c.grade)))
  return (
    <div className="tally">
      <div className="tally-row">
        <span className="tally-label">Is that true? {claims.length} claims checked:</span>
        {Object.entries(counts).map(([g, n]) => {
          const k = GRADE_CLASS[g] ?? { cls: 'g-interp', mark: '•' }
          return <button key={g} className={`grade ${k.cls} ${filter === g ? 'on' : ''}`} aria-pressed={filter === g} onClick={() => setFilter(filter === g ? null : g)} title={GRADE_INFO[g]?.blurb}>
            <span className="mark">{k.mark}</span> {n} {g}</button>
        })}
      </div>
      {list.length > 0 && <div className="flagged">{list.map(c => {
        const k = GRADE_CLASS[c.grade] ?? { cls: 'g-interp', mark: '•' }
        return <button key={c.id} className={`flag ${k.cls}`} onClick={e => onClaim(c, e.currentTarget)}><b>{c.grade}</b><span>{c.text}</span></button>
      })}</div>}
      {!filter && list.length === 0 && <p className="tally-note">Every claim in this chapter is backed by its sources. Tap any mark to see them.</p>}
    </div>
  )
}

function ClaimDrawer({ claim, onClose }: { claim: GradedClaim; onClose: () => void }) {
  const info = GRADE_INFO[claim.grade]
  const k = GRADE_CLASS[claim.grade] ?? { cls: 'g-interp', mark: '•' }
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <button className="close" ref={closeRef} onClick={onClose} aria-label="Close">✕</button>
        <p className="eyebrow">Is that true?</p>
        <h3 id="drawer-title">“{claim.text}”</h3>
        <div className={`verdict ${k.cls}`}><b><span className="mark">{k.mark}</span> {claim.grade}</b><span>{info?.blurb}</span></div>
        <p className="note"><b>Skeptic's note:</b> {claim.note.replace(/\b(?:evidence )?cards\b/gi, 'sources').replace(/\b(?:evidence )?card\b/gi, 'source')}</p>
        <h4>Evidence</h4>
        {claim.evidence.length === 0 && <p className="muted">No evidence card supports this claim.</p>}
        {claim.evidence.map(e => (
          <blockquote key={e.id} className="evidence">
            <p>{e.snippet}</p>
            <footer><a href={e.url} target="_blank" rel="noreferrer">{e.page_title}</a> · {e.pack === 'history' ? 'Wikipedia' : e.pack === 'star_wars' ? 'Wookieepedia' : e.pack === 'warhammer40k' ? 'Warhammer 40k Wiki' : e.pack} · {e.license}</footer>
          </blockquote>))}
      </div>
    </div>
  )
}

function AgentPanel({ activity }: { activity: Record<string, AgentActivity> }) {
  return (
    <div className="agents">
      <h4>The agents</h4>
      {AGENTS.map(a => {
        const act = activity[a.id]
        return (
          <div key={a.id} className={`agent ${act?.state ?? 'idle'}`}>
            <span className="glyph" aria-hidden>{a.glyph}</span>
            <div><b>{a.name}</b><small>{act?.state === 'working' ? (act.lastTool ?? act.label) : act?.state === 'done' ? `${act.label} · ${act.seconds}s` : a.role}</small></div>
            <span className="state">{act?.state === 'working' ? 'working' : act?.state === 'done' ? '✓' : act?.state === 'error' ? '!' : ''}</span>
          </div>)
      })}
    </div>
  )
}

function SpendMeter({ spend, episode, budget }: { spend: Spend | null; episode: Partial<Episode>; budget: number }) {
  const agents = spend?.agents ?? episode.usage ?? []
  const total = spend?.total_usd ?? episode.total_usd ?? 0
  const cap = spend?.budget_usd ?? budget
  const tokens = agents.reduce((s, a) => ({ in: s.in + a.input_tokens, cached: s.cached + a.cached_tokens, out: s.out + a.output_tokens }), { in: 0, cached: 0, out: 0 })
  return (
    <div className="meter">
      <h4>Cost meter <span className="muted">gpt-6-luna</span></h4>
      <div className="thermo"><div style={{ width: `${Math.min(100, (total / cap) * 100)}%` }} /></div>
      <p className="big">{fmtUsd(total)} <span className="muted">of {fmtUsd(cap)} cap</span></p>
      <p className="muted small">{tokens.in.toLocaleString()} in ({tokens.cached.toLocaleString()} cached) · {tokens.out.toLocaleString()} out</p>
      {agents.map(a => (
        <div key={a.agent} className="bar"><span>{a.agent}</span><div><i style={{ width: `${Math.min(100, (a.cost_usd / Math.max(total, 1e-9)) * 100)}%` }} /></div><em>{fmtUsd(a.cost_usd)}</em></div>))}
    </div>
  )
}
