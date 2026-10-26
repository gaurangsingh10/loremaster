import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { onSampleChange, sampleState, stopSample, toggleSample } from '../sample'
import { IconPause, IconSpeaker } from '../icons'
import { TOPICS, WORLDS, voiceId, type Prefs, type User } from '../prefs'
import type { Health } from '../types'
import Curtain from './Curtain'

export type Section = 'narrator' | 'stories' | 'appearance' | 'playback' | 'account' | 'privacy' | 'safety'
const SECTIONS: [Section, string, string][] = [
  ['narrator', '🎙', 'Narrator'], ['stories', '📜', 'Stories'], ['appearance', '🎨', 'Appearance'], ['playback', '▶', 'Playback'],
  ['account', '👤', 'Account'], ['privacy', '🔒', 'Privacy & data'], ['safety', '⛨', 'Safety & transparency'],
]

function Toggle({ on, onChange, label, hint }: { on: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="toggle-row">
      <span><b>{label}</b>{hint && <small className="muted">{hint}</small>}</span>
      <button role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? 'on' : ''}`} onClick={() => onChange(!on)}><span /></button>
    </label>)
}

function Seg<T extends string | number>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return <div className="seg" role="group" aria-label={label}>{options.map(([v, l]) =>
    <button key={String(v)} className={value === v ? 'on' : ''} aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>)}</div>
}

export default function Settings({ user, prefs, health, episodeId, section, onSection, onSave, onUser, onLogout, onQuiz, onAccount }: {
  user: User | null; prefs: Prefs; health: Health | null; episodeId: string | null; section: Section; onSection: (s: Section) => void
  onSave: (p: Prefs) => Promise<void>; onUser: (u: User | null) => void; onLogout: () => void; onQuiz: () => void; onAccount: () => void
}) {
  const [p, setP] = useState<Prefs>(prefs)
  const [saved, setSaved] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const [, force] = useState(0)
  useEffect(() => setP(prefs), [prefs])
  useEffect(() => { const off = onSampleChange(() => force(x => x + 1)); return () => { off(); stopSample() } }, [])
  const sample = sampleState()
  const playingMine = sample.playing && sample.voice === voiceId(p)

  // Every change saves itself (debounced), so there's no "Save" button to forget.
  function set(patch: Partial<Prefs>) {
    const next = { ...p, ...patch }; setP(next); setSaved(false)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => onSave(next).then(() => { setSaved(true); window.setTimeout(() => setSaved(false), 1800) }), 350)
  }

  return (
    <div className="settings">
      <div className="settings-head">
        <h2>Settings</h2>
        <p className="muted small">{user ? <>Signed in as <b>{user.email}</b>; settings follow your account.</> : 'Not signed in: settings live in this browser only.'}
          {' '}<span className={`saved ${saved ? 'show' : ''}`} aria-live="polite">{saved ? '✓ Saved' : ''}</span></p>
      </div>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {SECTIONS.map(([id, icon, label]) => (
            <button key={id} className={section === id ? 'on' : ''} aria-current={section === id ? 'page' : undefined} onClick={() => onSection(id)}>
              <span aria-hidden>{icon}</span>{label}</button>))}
        </nav>
        <div className="settings-body">
          {section === 'narrator' && <section className="card pref-card">
            <h3>Narrator</h3>
            <div className="pref-row"><span>Voice</span><Seg label="Voice" value={p.voice_gender} onChange={v => set({ voice_gender: v })} options={[['male', 'Man'], ['female', 'Woman']]} /></div>
            <div className="pref-row"><span>Accent</span><Seg label="Accent" value={p.accent} onChange={v => set({ accent: v })} options={[['uk', '🇬🇧 English (UK)'], ['us', '🇺🇸 English (US)']]} />
              <span className="sticker">More languages coming soon</span></div>
            <div className="pref-row"><span>Tone</span><Seg label="Tone" value={p.tone} onChange={v => set({ tone: v })} options={[['deep', 'Deep & slow'], ['natural', 'Natural']]} /></div>
            <div className="pref-row"><span>Speed</span><input type="range" min={0.8} max={1.4} step={0.05} value={p.speed} onChange={e => set({ speed: Number(e.target.value) })} aria-label="Default speed" /><b>{p.speed.toFixed(2)}×</b></div>
            <button className={`ghost preview ${playingMine ? 'on' : ''}`} aria-pressed={playingMine} onClick={() => toggleSample(voiceId(p))}>
              {playingMine ? <><IconPause /> Pause sample</> : <><IconSpeaker /> Hear this narrator</>}</button>
          </section>}

          {section === 'stories' && <section className="card pref-card">
            <h3>Stories</h3>
            {prefs.persona && <p className="muted small">Your quiz says you're <b className="gold">{prefs.persona}</b>.</p>}
            <div className="pref-row wrap"><span>I like</span><div className="chips-row" role="group" aria-label="Story types (pick any)">
              {TOPICS.map(t => <button key={t.id} className={`world ${p.interests.includes(t.id) ? 'on' : ''}`} aria-pressed={p.interests.includes(t.id)}
                onClick={() => set({ interests: p.interests.includes(t.id) ? p.interests.filter(x => x !== t.id) : [...p.interests, t.id] })}>{t.glyph} {t.label}</button>)}
              <button className={`world ${p.interests.length === 0 ? 'on' : ''}`} aria-pressed={p.interests.length === 0} onClick={() => set({ interests: [] })}>✦ Surprise me</button>
            </div></div>
            <p className="muted small pref-hint">Pick as many as you like; the home shelf mixes them. “Surprise me” shows a bit of everything.</p>
            <div className="pref-row wrap"><span>Worlds</span><div className="chips-row">
              {WORLDS.map(w => <button key={w.id} className={`world ${p.worlds.includes(w.id) ? 'on' : ''}`} aria-pressed={p.worlds.includes(w.id)}
                onClick={() => set({ worlds: p.worlds.includes(w.id) ? p.worlds.filter(x => x !== w.id) : [...p.worlds, w.id] })}>{w.glyph} {w.label}</button>)}</div></div>
            <div className="pref-row"><span>Length</span><Seg label="Length" value={p.minutes} onChange={v => set({ minutes: v })} options={[[10, '10 min'], [20, '20 min'], [40, '40 min']]} /></div>
            <button className="ghost" onClick={onQuiz}>Retake the 15-second quiz</button>
          </section>}

          {section === 'appearance' && <section className="card pref-card">
            <h3>Appearance</h3>
            <div className="theme-pick" role="radiogroup" aria-label="Theme">
              {([['dark', 'Night manuscript', 'Gold on midnight ink'], ['light', 'Day parchment', 'Ink on warm paper'], ['system', 'Match my device', 'Follows your OS setting']] as const).map(([t, l, d]) => (
                <button key={t} role="radio" aria-checked={p.theme === t} className={`theme-opt ${t} ${p.theme === t ? 'on' : ''}`} onClick={() => set({ theme: t })}>
                  <span className="swatch" aria-hidden><i /><i /><i /></span><b>{l}</b><small>{d}</small></button>))}
            </div>
            <div className="pref-row"><span>Text size</span><Seg label="Text size" value={p.text_size} onChange={v => set({ text_size: v })} options={[['normal', 'A'], ['large', 'A+'], ['xlarge', 'A++']]} /></div>
            <Toggle label="Reduce motion" hint="Turns off card tilts, fades and smooth scrolling." on={p.reduce_motion} onChange={v => set({ reduce_motion: v })} />
          </section>}

          {section === 'playback' && <section className="card pref-card">
            <h3>Playback</h3>
            <Toggle label="Read answers aloud" hint="Ask the narrator and interview answers start playing as soon as they arrive." on={p.auto_read} onChange={v => set({ auto_read: v })} />
            <Toggle label="Keep playing after I choose a branch" hint="The next chapter starts by itself when it's ready." on={p.autoplay_next} onChange={v => set({ autoplay_next: v })} />
            <p className="muted small">Keyboard: <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> skip 15 s · <kbd>Shift</kbd>+<kbd>←</kbd>/<kbd>→</kbd> previous/next section · <kbd>Esc</kbd> close panels.</p>
          </section>}

          {section === 'account' && <AccountSection user={user} onUser={onUser} onLogout={onLogout} onAccount={onAccount} />}

          {section === 'privacy' && <PrivacySection p={p} set={set} />}

          {section === 'safety' && <section className="safety-section">
            <div className="card pref-card">
              <h3>Safety &amp; transparency</h3>
              <p className="muted">How Loremaster keeps stories honest and safe, shown working: run the attacks yourself with defenses on and off, see what each story cost, and how listeners use the interactive features.</p>
              <ul className="safety-points">
                <li>Every claim is graded against real sources; invented facts are flagged <b>Unsupported</b>.</li>
                <li>Hidden instructions in wiki pages are stripped and quarantined before any AI reads them.</li>
                <li>Harmful-history requests, partisan campaigning, living-person role-play and face identification are refused.</li>
                <li>Every story has a hard spending cap, and you can stop it at any time.</li>
              </ul>
            </div>
            <Curtain episodeId={episodeId} health={health} />
          </section>}
        </div>
      </div>
    </div>
  )
}

function AccountSection({ user, onUser, onLogout, onAccount }: { user: User | null; onUser: (u: User | null) => void; onLogout: () => void; onAccount: () => void }) {
  const [name, setName] = useState(user?.name ?? '')
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [show, setShow] = useState(false)
  const [msg, setMsg] = useState<Record<string, { ok: boolean; text: string }>>({})
  const [del, setDel] = useState('')
  const [confirmDel, setConfirmDel] = useState(false)
  useEffect(() => setName(user?.name ?? ''), [user])
  const say = (k: string, ok: boolean, text: string) => setMsg(m => ({ ...m, [k]: { ok, text } }))

  if (!user) return (
    <section className="card pref-card">
      <h3>Account</h3>
      <p>Create a free account to keep your narrator, theme and story preferences on every device.</p>
      <button className="primary" onClick={onAccount}>Create account / Log in</button>
    </section>)

  async function saveName(e: React.FormEvent) {
    e.preventDefault()
    try { const r = await api<{ user: User }>('/api/me/name', { method: 'PUT', body: JSON.stringify({ name }) }); onUser(r.user); say('name', true, 'Name updated.') }
    catch (e: any) { say('name', false, e.message) }
  }
  async function changePw(e: React.FormEvent) {
    e.preventDefault()
    if (pw.next !== pw.confirm) return say('pw', false, 'The new passwords don’t match.')
    if (pw.next.length < 8) return say('pw', false, 'Use at least 8 characters.')
    try {
      await api('/api/me/password', { method: 'POST', body: JSON.stringify({ current: pw.current, new: pw.next }) })
      setPw({ current: '', next: '', confirm: '' }); say('pw', true, 'Password changed. Other devices have been signed out.')
    } catch (e: any) { say('pw', false, e.message) }
  }
  async function others() {
    try { const r = await api<{ ended: number }>('/api/me/logout-others', { method: 'POST' }); say('sess', true, r.ended ? `Signed out of ${r.ended} other session${r.ended > 1 ? 's' : ''}.` : 'No other sessions were signed in.') }
    catch (e: any) { say('sess', false, e.message) }
  }
  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault()
    try { await api('/api/me/delete', { method: 'POST', body: JSON.stringify({ password: del }) }); onLogout(); onUser(null) }
    catch (e: any) { say('del', false, e.message) }
  }
  const Msg = ({ k }: { k: string }) => msg[k] ? <p className={msg[k].ok ? 'ok-text' : 'error'} role="status">{msg[k].text}</p> : null
  const type = show ? 'text' : 'password'

  return (
    <div className="account-sections">
      <section className="card pref-card">
        <h3>Profile</h3>
        <form className="form-grid" onSubmit={saveName}>
          <label>Display name<input value={name} maxLength={60} onChange={e => setName(e.target.value)} /></label>
          <label>Email<input value={user.email} disabled /></label>
          <button className="ghost" disabled={!name.trim() || name.trim() === user.name}>Save name</button>
        </form>
        <Msg k="name" />
      </section>
      <section className="card pref-card">
        <h3>Change password</h3>
        <form className="form-grid" onSubmit={changePw}>
          <label>Current password<input type={type} autoComplete="current-password" value={pw.current} onChange={e => setPw({ ...pw, current: e.target.value })} required /></label>
          <label>New password<input type={type} autoComplete="new-password" minLength={8} value={pw.next} onChange={e => setPw({ ...pw, next: e.target.value })} required /></label>
          <label>Confirm new password<input type={type} autoComplete="new-password" value={pw.confirm} onChange={e => setPw({ ...pw, confirm: e.target.value })} required /></label>
          <label className="check"><input type="checkbox" checked={show} onChange={e => setShow(e.target.checked)} /> Show passwords</label>
          <button className="primary" disabled={!pw.current || !pw.next || !pw.confirm}>Change password</button>
        </form>
        <Msg k="pw" />
      </section>
      <section className="card pref-card">
        <h3>Sessions</h3>
        <div className="row"><button className="ghost" onClick={others}>Sign out of other devices</button><button className="ghost" onClick={onLogout}>Log out here</button></div>
        <Msg k="sess" />
      </section>
      <section className="card pref-card danger">
        <h3>Delete account</h3>
        <p className="muted small">Removes your account and saved preferences. Stories in the shared library stay.</p>
        {!confirmDel ? <button className="danger-btn" onClick={() => setConfirmDel(true)}>Delete my account…</button> :
          <form className="form-grid" onSubmit={deleteAccount}>
            <label>Type your password to confirm<input type="password" autoComplete="current-password" value={del} onChange={e => setDel(e.target.value)} required /></label>
            <div className="row"><button className="danger-btn" disabled={!del}>Delete permanently</button><button type="button" className="ghost" onClick={() => { setConfirmDel(false); setDel('') }}>Cancel</button></div>
          </form>}
        <Msg k="del" />
      </section>
    </div>)
}

function PrivacySection({ p, set }: { p: Prefs; set: (patch: Partial<Prefs>) => void }) {
  const [done, setDone] = useState('')
  function clearLocal() {
    const keep = new Set(['lm-prefs', 'lm-voice', 'lm-token'])
    Object.keys(localStorage).filter(k => k.startsWith('lm-') && !keep.has(k)).forEach(k => localStorage.removeItem(k))
    setDone('Cleared resume positions, removed-story list and other listening data on this device.')
  }
  return (
    <section className="card pref-card">
      <h3>Privacy &amp; data</h3>
      <Toggle label="Share anonymous usage stats" hint="Counts questions asked, calls made and quiz answers (no names, no audio) to measure curiosity. Turn off and nothing is sent."
        on={p.usage_stats} onChange={v => set({ usage_stats: v })} />
      <ul className="privacy-facts">
        <li>Photos for Snap &amp; Story are resized in your browser, used once and never stored.</li>
        <li>Passwords are stored only as salted scrypt hashes; sessions as SHA-256 hashes.</li>
        <li>No ads, no trackers, no third-party analytics.</li>
      </ul>
      <button className="ghost" onClick={clearLocal}>Clear listening data on this device</button>
      {done && <p className="ok-text" role="status">{done}</p>}
    </section>)
}
