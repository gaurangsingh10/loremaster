import { useEffect, useRef, useState } from 'react'
import { api, setToken } from '../api'
import { onSampleChange, sampleState, stopSample, toggleSample } from '../sample'
import { IconPause, IconSpeaker } from '../icons'
import { WORLDS, voiceId, type Prefs, type User } from '../prefs'

function strength(pw: string): { score: number; label: string } {
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  const label = ['Too short', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent'][Math.min(s, 5)]
  return { score: Math.min(s, 5), label }
}

function PasswordField({ label, value, onChange, autoComplete, invalid, describedBy, inputRef }: {
  label: string; value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean; describedBy?: string
  inputRef?: React.Ref<HTMLInputElement>
}) {
  const [show, setShow] = useState(false)
  return (
    <label>{label}
      <span className={`pw-wrap ${invalid ? 'invalid' : ''}`}>
        <input ref={inputRef} type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)} required
          autoComplete={autoComplete} aria-invalid={invalid || undefined} aria-describedby={describedBy} spellCheck={false} />
        <button type="button" className="eye" onClick={() => setShow(!show)} aria-pressed={show}
          aria-label={show ? 'Hide password' : 'Show password'} title={show ? 'Hide password' : 'Show password (only on your screen)'}>
          {show
            ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M3 3l18 18" /><path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c5 0 9 4.5 10 7-0.4 1-1.3 2.4-2.6 3.7M6.6 6.6C4.4 8 2.8 10.1 2 12c1 2.5 5 7 10 7 1.8 0 3.4-.6 4.8-1.4" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>
            : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M2 12c1-2.5 5-7 10-7s9 4.5 10 7c-1 2.5-5 7-10 7S3 14.5 2 12z" /><circle cx="12" cy="12" r="3" /></svg>}
        </button>
      </span>
    </label>
  )
}

export function AccountModal({ prefs, onClose, onAuthed }: { prefs: Prefs; onClose: () => void; onAuthed: (u: User) => void }) {
  const [mode, setMode] = useState<'signup' | 'login'>('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [human, setHuman] = useState(false)
  const [website, setWebsite] = useState('')          // honeypot (hidden from people)
  const [challenge, setChallenge] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const first = useRef<HTMLInputElement>(null)
  const loadChallenge = () => api<{ challenge: string }>('/api/auth/challenge').then(r => setChallenge(r.challenge)).catch(() => {})
  useEffect(() => { first.current?.focus(); setErr(''); setHuman(false); loadChallenge() }, [mode])
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [onClose])

  const st = strength(password)
  const mismatch = mode === 'signup' && confirm.length > 0 && confirm !== password
  const canSubmit = !busy && human && email && password && (mode === 'login' || (name.trim() && password.length >= 8 && confirm === password))

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    if (mode === 'signup' && password !== confirm) { setErr('Passwords don\'t match.'); return }
    if (!human) { setErr('Please tick “I\'m not a robot”.'); return }
    setBusy(true)
    try {
      const bot = { challenge, human, website }
      const body = mode === 'signup' ? { name, email, password, prefs, ...bot } : { email, password, ...bot }
      const r = await api<{ token: string; user: User }>(`/api/auth/${mode}`, { method: 'POST', body: JSON.stringify(body) })
      setToken(r.token); onAuthed(r.user); onClose()
    } catch (e: any) {
      setErr(typeof e.message === 'string' ? e.message : 'Something went wrong.')
      loadChallenge()   // challenges are single-form; fetch a fresh one for the retry
    } finally { setBusy(false) }
  }

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-labelledby="acct-title" onClick={onClose}>
      <form className="account card" onClick={e => e.stopPropagation()} onSubmit={submit} noValidate>
        <button type="button" className="close" aria-label="Close" onClick={onClose}>✕</button>
        <div className="acct-brand"><span className="sigil" aria-hidden>✦</span><span>Loremaster</span></div>
        <div className="seg acct-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'on' : ''} onClick={() => setMode('signup')}>Create account</button>
          <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'on' : ''} onClick={() => setMode('login')}>Log in</button>
        </div>
        <h2 id="acct-title">{mode === 'signup' ? 'Save your narrator and your stories' : 'Welcome back, loremaster'}</h2>
        {mode === 'signup' && <label>Name<input ref={first} value={name} onChange={e => setName(e.target.value)} required maxLength={60} autoComplete="name" placeholder="What should the narrator call you?" /></label>}
        <label>Email<input ref={mode === 'login' ? first : undefined} type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" placeholder="you@example.com" /></label>
        <PasswordField label="Password" value={password} onChange={setPassword} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} describedBy="pw-help" />
        {mode === 'signup' && <>
          <div className="pw-meter" id="pw-help" aria-live="polite">
            <div className="bars">{[1, 2, 3, 4, 5].map(i => <i key={i} className={password && i <= st.score ? `s${st.score}` : ''} />)}</div>
            <small>{password ? `${st.label}${password.length < 8 ? ' · at least 8 characters' : ''}` : 'At least 8 characters. Mix letters, numbers and a symbol.'}</small>
          </div>
          <PasswordField label="Confirm password" value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={mismatch} describedBy="pw-match" />
          <small id="pw-match" className={`match ${mismatch ? 'bad' : confirm && confirm === password ? 'ok' : ''}`} aria-live="polite">
            {mismatch ? 'Passwords don’t match yet' : confirm && confirm === password ? '✓ Passwords match' : ''}</small>
        </>}
        {/* honeypot: invisible to people and screen readers; bots that fill every field get rejected */}
        <input className="hp" tabIndex={-1} autoComplete="off" aria-hidden="true" name="website" value={website} onChange={e => setWebsite(e.target.value)} />
        <label className={`robot ${human ? 'on' : ''}`}>
          <input type="checkbox" checked={human} onChange={e => setHuman(e.target.checked)} />
          <span className="box" aria-hidden>{human ? '✓' : ''}</span>
          <span className="robot-text">I'm not a robot</span>
          <span className="robot-badge" aria-hidden>🛡 bot check</span>
        </label>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="primary" disabled={!canSubmit}>{busy ? 'One moment…' : mode === 'signup' ? 'Create account' : 'Log in'}</button>
        <p className="fine">Passwords are stored only as a salted scrypt hash. {mode === 'signup' ? <>Already have an account? <button type="button" className="linkish" onClick={() => setMode('login')}>Log in</button></> : <>New here? <button type="button" className="linkish" onClick={() => setMode('signup')}>Create an account</button></>}</p>
      </form>
    </div>
  )
}
