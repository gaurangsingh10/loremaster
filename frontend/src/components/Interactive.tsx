import { useEffect, useRef, useState } from 'react'
import { localPrefs } from '../prefs'
import { API, GRADE_INFO, api } from '../api'
import { logEvent } from '../events'
import { onSampleChange, sampleState, stopSample } from '../sample'
import { IconPause, IconSpeaker } from '../icons'
import type { Answer, CallIt, EvidenceCard, MythItem } from '../types'

const MARK: Record<string, string> = { Documented: 'D', Canon: 'C', Debated: '≈', Conflicting: '≠', Legend: 'L', Legends: 'L', 'Fan theory': 'F', Interpretation: 'i', Unsupported: '?' }
const CLS: Record<string, string> = { Documented: 'g-fact', Canon: 'g-fact', Debated: 'g-debated', Conflicting: 'g-debated', Legend: 'g-legend', Legends: 'g-legend', 'Fan theory': 'g-fan', Interpretation: 'g-interp', Unsupported: 'g-bad' }

function Sources({ cards }: { cards: EvidenceCard[] }) {
  if (!cards.length) return null
  return <p className="mini-sources">Source{cards.length > 1 ? 's' : ''}: {cards.map((e, i) => <span key={e.id}>{i > 0 && ' · '}<a href={e.url} target="_blank" rel="noreferrer">{e.page_title}</a></span>)}</p>
}

// ------------------------------------------------------------------ Ask the narrator
export function AskPanel({ episodeId, chapter, onClose, onPauseStory, onResumeStory, voice }: {
  episodeId: string; chapter: number; onClose: () => void; onPauseStory: () => void; onResumeStory: () => void; voice: string
}) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [answers, setAnswers] = useState<Answer[]>([])
  const [listening, setListening] = useState(false)
  const [playing, setPlaying] = useState<string | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const rec = useRef<any>(null)
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

  useEffect(() => { input.current?.focus(); onPauseStory(); stopSample()
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => { window.removeEventListener('keydown', k); audio.current?.pause(); rec.current?.abort?.() } }, [])  // eslint-disable-line

  function playAnswer(a: Answer) {
    if (playing === a.id && audio.current && !audio.current.paused) { audio.current.pause(); setPlaying(null); return }  // toggle
    audio.current?.pause()
    const el = new Audio(`${API}/api/answer/${a.id}/audio?voice=${voice}`)
    audio.current = el; setPlaying(a.id)
    el.onended = () => setPlaying(null)
    el.play().catch(() => setPlaying(null))
  }

  async function ask(e?: React.FormEvent) {
    e?.preventDefault()
    const question = q.trim(); if (!question || busy) return
    setBusy(true); setErr('')
    try {
      const a = await api<Answer>(`/api/episode/${episodeId}/ask`, { method: 'POST', body: JSON.stringify({ question, chapter }) })
      if (a.refused) { setErr(a.reason || 'I can’t answer that one.'); return }
      setAnswers(x => [a, ...x]); setQ('')
      if (localPrefs().auto_read) playAnswer(a)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  function mic() {
    if (!SR) return
    if (listening) { rec.current?.stop(); return }
    const r = new SR(); rec.current = r
    r.lang = 'en-GB'; r.interimResults = true; r.maxAlternatives = 1
    r.onresult = (ev: any) => { const t = Array.from(ev.results).map((x: any) => x[0].transcript).join(' '); setQ(t) }
    r.onend = () => setListening(false)
    r.onerror = () => setListening(false)
    setListening(true); r.start()
  }

  return (
    <div className="ask-panel" role="dialog" aria-label="Ask the narrator">
      <div className="ask-head"><b>💬 Ask the narrator</b><span className="muted small">The story is paused. Ask anything about this chapter.</span>
        <button className="close" onClick={onClose} aria-label="Close">✕</button></div>
      <form onSubmit={ask} className="ask-form">
        <input ref={input} value={q} onChange={e => setQ(e.target.value)} maxLength={300} placeholder={listening ? 'Listening…' : 'e.g. “Why did the Senate agree to that?”'} aria-label="Your question" />
        {SR && <button type="button" className={`mic ${listening ? 'on' : ''}`} onClick={mic} aria-pressed={listening} aria-label={listening ? 'Stop listening' : 'Ask by voice'} title="Ask by voice">🎙</button>}
        <button className="primary" disabled={busy || !q.trim()}>{busy ? 'Thinking…' : 'Ask'}</button>
      </form>
      {busy && <p className="muted small">The narrator is checking the sources…</p>}
      {err && <p className="error">{err}</p>}
      <div className="answers">
        {answers.map(a => (
          <div key={a.id} className="answer">
            <p className="q">“{a.question}”</p>
            <p className="a">{a.answer}</p>
            {a.claims.length > 0 && <div className="a-claims">{a.claims.map((c, i) => (
              <span key={i} className={`grade ${CLS[c.grade] ?? 'g-interp'}`} title={`${c.text}${c.evidence[0] ? ` (source: ${c.evidence[0].page_title})` : ''}`}><span className="mark">{MARK[c.grade] ?? '•'}</span> {c.grade}</span>))}</div>}
            <Sources cards={a.claims.flatMap(c => c.evidence).filter((e, i, arr) => arr.findIndex(x => x.id === e.id) === i)} />
            <button className={`ghost preview ${playing === a.id ? 'on' : ''}`} onClick={() => playAnswer(a)}>{playing === a.id ? <><IconPause /> Pause answer</> : <><IconSpeaker /> Hear the answer</>}</button>
          </div>))}
      </div>
      <button className="primary resume" onClick={() => { audio.current?.pause(); onClose(); onResumeStory() }}>▶ Back to the story</button>
    </div>
  )
}

// ------------------------------------------------------------------ Myth or Fact?
export function MythOrFact({ items, episodeId, chapter }: { items: MythItem[]; episodeId: string; chapter: number }) {
  const [i, setI] = useState(0)
  const [pick, setPick] = useState<string | null>(null)
  const [score, setScore] = useState(0)
  const [streak, setStreak] = useState(Number(localStorage.getItem('lm-streak') || 0))
  if (!items.length) return null
  const done = i >= items.length
  const it = items[Math.min(i, items.length - 1)]

  function answer(v: 'fact' | 'myth' | 'debated') {
    if (pick) return
    const correct = v === it.verdict
    setPick(v)
    if (correct) setScore(s => s + 1)
    const ns = correct ? streak + 1 : 0
    setStreak(ns); localStorage.setItem('lm-streak', String(ns))
    logEvent('myth_answer', episodeId, chapter, { statement: it.statement.slice(0, 120), verdict: it.verdict, answer: v, correct })
  }

  return (
    <section className="game myth" aria-label="Myth or Fact">
      <div className="game-head"><span className="game-title">Myth or Fact?</span>
        <span className="game-meta">{done ? `You got ${score} of ${items.length}` : `${i + 1} of ${items.length}`} · 🔥 streak {streak}</span></div>
      {!done ? <>
        <p className="statement">“{it.statement}”</p>
        <div className="game-buttons">
          {(['fact', 'debated', 'myth'] as const).map(v => (
            <button key={v} className={`gbtn ${pick === v ? (v === it.verdict ? 'right' : 'wrong') : ''} ${pick && v === it.verdict ? 'right' : ''}`} disabled={!!pick} onClick={() => answer(v)}>
              {v === 'fact' ? 'Fact' : v === 'myth' ? 'Myth' : 'Debated'}</button>))}
        </div>
        {pick && <div className={`reveal ${pick === it.verdict ? 'ok' : 'bad'}`} role="status">
          <b>{pick === it.verdict ? 'Correct!' : 'Not quite.'} It’s {it.verdict === 'fact' ? 'a fact' : it.verdict === 'myth' ? 'a myth' : 'debated'}.</b> {it.explanation}
          <Sources cards={it.evidence} />
          <button className="primary small-next" onClick={() => { setPick(null); setI(i + 1) }}>{i + 1 < items.length ? 'Next →' : 'See score'}</button>
        </div>}
      </> : <p className="statement small">{score === items.length ? 'Perfect round. You can tell legend from history.' : score >= 2 ? 'Sharp ear. Most people miss at least one.' : 'Tricky, right? That’s why every claim is graded.'}</p>}
    </section>
  )
}

// ------------------------------------------------------------------ Call it
export function CallItCard({ call, episodeId, chapter, onAnswered }: { call: CallIt; episodeId: string; chapter: number; onAnswered: () => void }) {
  const [pick, setPick] = useState<number | null>(null)
  function choose(k: number) {
    if (pick !== null) return
    setPick(k)
    logEvent('callit_answer', episodeId, chapter, { question: call.question.slice(0, 120), answer: k, correct: k === call.answer_index })
    setTimeout(onAnswered, 900)
  }
  return (
    <section className="game callit" aria-label="Call it">
      <div className="game-head"><span className="game-title">🎯 Call it</span><span className="game-meta">Before you hear what happened…</span></div>
      <p className="statement">{call.question}</p>
      <div className="game-buttons col">
        {call.options.map((o, k) => <button key={k} className={`gbtn ${pick !== null && k === call.answer_index ? 'right' : pick === k ? 'wrong' : ''}`} disabled={pick !== null} onClick={() => choose(k)}>{o}</button>)}
      </div>
      {pick !== null && <p className={`reveal ${pick === call.answer_index ? 'ok' : 'bad'}`}><b>{pick === call.answer_index ? 'You called it!' : 'Good guess, but no.'}</b> Listen on…</p>}
      {pick === null && <button className="linkish skip" onClick={onAnswered}>Skip</button>}
    </section>
  )
}

export function useSampleTick() { const [, f] = useState(0); useEffect(() => onSampleChange(() => f(x => x + 1)), []); return sampleState() }
