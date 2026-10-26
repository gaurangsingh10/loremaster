import { useEffect, useRef, useState } from 'react'
import { API, api } from '../api'
import { IconPause, IconSpeaker } from '../icons'
import { localPrefs, type Prefs } from '../prefs'
import type { EvidenceCard } from '../types'
import { coverUrl, creditText, useCovers } from '../covers'

interface Char { id: string; name: string; pack: string; era: string; glyph: string; gender: string; greeting: string }
interface Turn { q: string; answer?: string; aside?: string; claims?: { text: string; grade: string; evidence: EvidenceCard[] }[]; id?: string; error?: string }
const MARK: Record<string, string> = { Documented: 'D', Canon: 'C', Debated: '≈', Conflicting: '≠', Legend: 'L', Legends: 'L', 'Fan theory': 'F', Interpretation: 'i', Unsupported: '?' }
const CLS: Record<string, string> = { Documented: 'g-fact', Canon: 'g-fact', Debated: 'g-debated', Conflicting: 'g-debated', Legend: 'g-legend', Legends: 'g-legend', 'Fan theory': 'g-fan', Interpretation: 'g-interp', Unsupported: 'g-bad' }
const PACK: Record<string, string> = { history: 'History', politics: 'Politics', science: 'Science', technology: 'Technology', star_wars: 'Star Wars', warhammer40k: 'Warhammer 40K' }

export default function Interview({ prefs, health }: { prefs: Prefs; health: any }) {
  const covers = useCovers()
  const [chars, setChars] = useState<Char[]>([])
  const [sid, setSid] = useState<string | null>(null)
  const [who, setWho] = useState<Char | null>(null)
  const [custom, setCustom] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [playing, setPlaying] = useState<string | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { api('/api/interview/characters').then(r => setChars(r.characters)).catch(() => {}) }, [])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, busy])
  useEffect(() => () => audio.current?.pause(), [])

  const voiceFor = (c: Char | null) => `${c?.gender === 'female' ? 'female' : 'male'}-${prefs.accent}-${prefs.tone}`
  function hear(t: Turn) {
    if (!t.id) return
    if (playing === t.id && audio.current && !audio.current.paused) { audio.current.pause(); setPlaying(null); return }
    audio.current?.pause()
    const a = new Audio(`${API}/api/answer/${t.id}/audio?voice=${voiceFor(who)}`); audio.current = a; setPlaying(t.id)
    a.onended = () => setPlaying(null); a.play().catch(() => setPlaying(null))
  }
  async function start(c: Char | null, name?: string) {
    setErr(''); setBusy('Summoning…')
    try {
      const r = await api('/api/interview/start', { method: 'POST', body: JSON.stringify(c ? { character_id: c.id } : { custom_name: name }) })
      setSid(r.sid); setWho(r.character); setTurns([])
    } catch (e: any) { setErr(e.message) } finally { setBusy('') }
  }
  async function ask(e?: React.FormEvent) {
    e?.preventDefault(); const question = q.trim(); if (!question || !sid) return
    setQ(''); setTurns(t => [...t, { q: question }]); setBusy(`${who?.name.split(' ')[0]} is thinking…`)
    try {
      const r = await api(`/api/interview/${sid}/ask`, { method: 'POST', body: JSON.stringify({ question }) })
      const turn: Turn = r.refused ? { q: question, error: r.reason } : { q: question, answer: r.answer, aside: r.aside, claims: r.claims, id: r.id }
      setTurns(t => [...t.slice(0, -1), turn]); if (turn.id && localPrefs().auto_read) hear(turn)
    } catch (e: any) { setTurns(t => [...t.slice(0, -1), { q: question, error: e.message }]) } finally { setBusy('') }
  }

  if (!sid) return (
    <div className="interview">
      <p className="eyebrow">Interview the past</p>
      <h2>Ask them yourself.</h2>
      <p className="lede">Question emperors, scientists, rebels and Sith Lords. They answer in character; Loremaster grades every claim, because Caesar always flattered Caesar.</p>
      {health?.demo_only && <p className="demo-note">Interviews need an API key.</p>}
      <div className="char-grid">
        {chars.map(c => (
          <button key={c.id} className="char" disabled={!!busy || health?.demo_only} onClick={() => start(c)}>
            {covers['g-' + c.id] ? <img className="char-cover" src={coverUrl('g-' + c.id)} alt="" loading="lazy" title={creditText(covers['g-' + c.id])} /> : <span className="char-glyph" aria-hidden>{c.glyph}</span>}<b>{c.name}</b><small>{c.era}</small><span className="tag">{PACK[c.pack] ?? c.pack}</span>
          </button>))}
      </div>
      <form className="dc-form" onSubmit={e => { e.preventDefault(); if (custom.trim()) start(null, custom.trim()) }}>
        <input value={custom} onChange={e => setCustom(e.target.value)} maxLength={80} placeholder="Or name anyone from history or lore (e.g. Hannibal, Cleopatra, Ahsoka Tano)" aria-label="Custom character" />
        <button className="primary" disabled={!!busy || !custom.trim()}>{busy || 'Summon'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      <p className="muted small">Living people can't be interviewed, and perpetrators of atrocities aren't voiced in character.</p>
    </div>
  )

  return (
    <div className="interview chat">
      <div className="iv-head">
        {who && covers['g-' + who.id] ? <img className="char-portrait" src={coverUrl('g-' + who.id)} alt={who.name} title={creditText(covers['g-' + who.id])} /> : <span className="char-glyph big" aria-hidden>{who?.glyph}</span>}
        <div><p className="eyebrow">In conversation with</p><h2>{who?.name}</h2><p className="muted small">{who?.era} · answers in character · every claim graded</p></div>
        <button className="ghost" onClick={() => { audio.current?.pause(); setSid(null); setWho(null) }}>Change guest</button>
      </div>
      <div className="iv-log">
        <div className="bubble them"><p className="in-char">{who?.greeting}</p></div>
        {turns.map((t, i) => (
          <div key={i}>
            <div className="bubble me">{t.q}</div>
            {t.error && <div className="bubble them"><p className="error">{t.error}</p></div>}
            {t.answer && <div className="bubble them">
              <p className="in-char">{t.answer}</p>
              {t.aside && <p className="aside">🎙 Narrator: {t.aside}</p>}
              {t.claims && t.claims.length > 0 && <div className="a-claims">{t.claims.map((c, k) => (
                <span key={k} className={`grade ${CLS[c.grade] ?? 'g-interp'}`} title={`${c.text}${c.evidence[0] ? ` (source: ${c.evidence[0].page_title})` : ''}`}><span className="mark">{MARK[c.grade] ?? '•'}</span> {c.grade}</span>))}</div>}
              {t.claims && t.claims.some(c => c.evidence.length) && <p className="mini-sources">Sources: {[...new Map(t.claims.flatMap(c => c.evidence).map(e => [e.page_title, e])).values()].map((e, k) => <span key={e.page_title}>{k > 0 && ' · '}<a href={e.url} target="_blank" rel="noreferrer">{e.page_title}</a></span>)}</p>}
              <button className={`ghost preview ${playing === t.id ? 'on' : ''}`} onClick={() => hear(t)}>{playing === t.id ? <><IconPause /> Pause</> : <><IconSpeaker /> Hear it</>}</button>
            </div>}
          </div>))}
        {busy && <div className="bubble them"><p className="muted">{busy}</p></div>}
        <div ref={end} />
      </div>
      <form className="dc-form iv-form" onSubmit={ask}>
        <input value={q} onChange={e => setQ(e.target.value)} maxLength={300} placeholder={`Ask ${who?.name.split(' ')[0]} anything…`} aria-label="Your question" autoFocus />
        <button className="primary" disabled={!!busy || !q.trim()}>Ask</button>
      </form>
    </div>
  )
}
