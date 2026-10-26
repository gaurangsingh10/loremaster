import { useEffect, useState } from 'react'
import { TOPICS, WORLDS, personaFor, voiceId, type Prefs } from '../prefs'
import { onSampleChange, playSample, sampleState, stopSample, toggleSample } from '../sample'
import { IconChevronLeft, IconPause, IconSpeaker } from '../icons'

// A 5-tap onboarding quiz (~15 seconds). Each answer auto-advances, except "worlds" (multi-select).
export default function Onboarding({ initial, onDone, onSkip, loggedIn, onAccount }: {
  initial: Prefs; onDone: (p: Prefs) => void; onSkip: () => void; loggedIn: boolean; onAccount: () => void
}) {
  const [p, setP] = useState<Prefs>({ ...initial })
  const [step, setStep] = useState(0)
  const [t0] = useState(Date.now())
  const [secs, setSecs] = useState(0)
  const [, force] = useState(0)
  useEffect(() => onSampleChange(() => force(x => x + 1)), [])
  const sample = sampleState()
  const total = 5

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onSkip() }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); stopSample() }
  }, [onSkip])

  const set = (patch: Partial<Prefs>, advance = true) => { setP(x => ({ ...x, ...patch })); if (advance) setTimeout(() => setStep(s => Math.min(s + 1, total - 1)), 180) }
  useEffect(() => { if (step === total - 1) setSecs(Math.round((Date.now() - t0) / 1000)) }, [step, t0])

  const myVoice = voiceId(p)
  const playingMine = sample.playing && sample.voice === myVoice
  // picking an option plays that narrator; tapping the option that's already playing pauses it
  const pick = (patch: Partial<Prefs>) => {
    const next = { ...p, ...patch }
    const v = voiceId(next)
    if (v === myVoice && playingMine) { stopSample(); return }
    set(patch, false); playSample(v)
  }

  const persona = personaFor(p)
  const Opt = ({ on, onClick, title, sub, glyph }: { on: boolean; onClick: () => void; title: string; sub?: string; glyph?: string }) => (
    <button className={`quiz-opt ${on ? 'on' : ''}`} onClick={onClick} aria-pressed={on}>
      {glyph && <span className="qglyph" aria-hidden>{glyph}</span>}<b>{title}</b>{sub && <small>{sub}</small>}
    </button>)

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-labelledby="quiz-title">
      <div className="quiz">
        <div className="quiz-top">
          <button className="quiz-back" onClick={() => { stopSample(); setStep(step - 1) }} disabled={step === 0} aria-label="Previous question"
            style={{ visibility: step > 0 && step < 4 ? 'visible' : 'hidden' }}><IconChevronLeft /> Back</button>
          <div className="quiz-dots" aria-label={`Step ${step + 1} of ${total}`}>{Array.from({ length: total }).map((_, i) => <i key={i} className={i <= step ? 'on' : ''} />)}</div>
          <button className="quiz-skip" onClick={onSkip}>Skip</button>
        </div>

        {step === 0 && <>
          <p className="eyebrow">15 seconds to your perfect story</p>
          <h2 id="quiz-title">What pulls you in?</h2>
          <p className="muted">Pick as many as you like.</p>
          <div className="quiz-grid three">
            {TOPICS.map(t => <Opt key={t.id} on={p.interests.includes(t.id)} glyph={t.glyph} title={t.id === 'crossover' ? 'The history behind the lore' : t.label} sub={t.sub}
              onClick={() => set({ interests: p.interests.includes(t.id) ? p.interests.filter(x => x !== t.id) : [...p.interests, t.id] }, false)} />)}
            <Opt on={p.interests.length === 0} onClick={() => set({ interests: [] }, false)} glyph="✦" title="Surprise me" sub="A bit of everything" />
          </div>
          <button className="primary quiz-next" onClick={() => setStep(1)}>{p.interests.length ? `Next →` : 'Surprise me →'}</button>
        </>}

        {step === 1 && <>
          <h2 id="quiz-title">Pick your worlds</h2>
          <p className="muted">Tap all that apply.</p>
          <div className="quiz-grid three">
            {WORLDS.map(w => <Opt key={w.id} on={p.worlds.includes(w.id)} glyph={w.glyph} title={w.label}
              onClick={() => set({ worlds: p.worlds.includes(w.id) ? p.worlds.filter(x => x !== w.id) : [...p.worlds, w.id] }, false)} />)}
          </div>
          <button className="primary quiz-next" onClick={() => setStep(2)}>{p.worlds.length ? 'Next →' : 'Any world is fine →'}</button>
        </>}

        {step === 2 && <>
          <h2 id="quiz-title">How long do you listen?</h2>
          <div className="quiz-grid three">
            <Opt on={p.minutes === 10} onClick={() => set({ minutes: 10 })} glyph="☕" title="10 min" sub="A short walk" />
            <Opt on={p.minutes === 20} onClick={() => set({ minutes: 20 })} glyph="🚆" title="20 min" sub="A typical commute" />
            <Opt on={p.minutes === 40} onClick={() => set({ minutes: 40 })} glyph="🛤" title="40 min" sub="The long haul" />
          </div>
        </>}

        {step === 3 && <>
          <h2 id="quiz-title">Choose your narrator</h2>
          <div className="voice-pick">
            <div className="seg" role="group" aria-label="Voice">
              {(['male', 'female'] as const).map(g => <button key={g} className={p.voice_gender === g ? 'on' : ''} onClick={() => pick({ voice_gender: g })}>{g === 'male' ? 'Man' : 'Woman'}</button>)}
            </div>
            <div className="accent-row">
              <div className="seg" role="group" aria-label="Accent">
                {(['uk', 'us'] as const).map(a => <button key={a} className={p.accent === a ? 'on' : ''} onClick={() => pick({ accent: a })}>{a === 'uk' ? '🇬🇧 English (UK)' : '🇺🇸 English (US)'}</button>)}
              </div>
              <span className="sticker" title="Spanish, Hindi, French and Japanese narrators are on the roadmap">More languages coming soon</span>
            </div>
            <div className="seg" role="group" aria-label="Tone">
              {(['deep', 'natural'] as const).map(t => <button key={t} className={p.tone === t ? 'on' : ''} onClick={() => pick({ tone: t })}>{t === 'deep' ? 'Deep & slow' : 'Natural'}</button>)}
            </div>
            <button className={`ghost preview ${playingMine ? 'on' : ''}`} aria-pressed={playingMine} onClick={() => toggleSample(myVoice)}>
              {playingMine ? <><IconPause /> Pause sample</> : <><IconSpeaker /> Hear this narrator</>}</button>
          </div>
          <button className="primary quiz-next" onClick={() => { stopSample(); setStep(4) }}>That's my narrator →</button>
        </>}

        {step === 4 && <>
          <p className="eyebrow">Your Loremaster profile{secs ? ` · done in ${secs}s` : ''}</p>
          <h2 id="quiz-title" className="persona">{persona.name}</h2>
          <p className="lede">{persona.blurb}</p>
          <ul className="profile-summary">
            <li><b>Stories:</b> {p.interests.length ? p.interests.map(i => TOPICS.find(t => t.id === i)?.label.toLowerCase()).join(', ') : 'a mix'}{p.worlds.length ? ` · ${p.worlds.map(w => WORLDS.find(x => x.id === w)?.label).join(', ')}` : ''}</li>
            <li><b>Length:</b> {p.minutes} minutes</li>
            <li><b>Narrator:</b> {p.accent === 'uk' ? 'UK' : 'US'} {p.voice_gender === 'male' ? 'man' : 'woman'}, {p.tone === 'deep' ? 'deep & slow' : 'natural'}</li>
          </ul>
          <div className="row">
            <button className="primary" onClick={() => onDone({ ...p, persona: persona.name, onboarded: true })}>Start listening →</button>
            {!loggedIn && <button className="ghost" onClick={() => { onDone({ ...p, persona: persona.name, onboarded: true }); onAccount() }}>Save to an account</button>}
          </div>
        </>}

      </div>
    </div>
  )
}
