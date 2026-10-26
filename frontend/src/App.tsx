import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'
import { applyAppearance, localPrefs, normalize, savePrefs, voiceId, type Prefs, type User } from './prefs'
import Onboarding from './components/Onboarding'
import { AccountModal } from './components/Account'
import Settings, { type Section } from './components/Settings'
import type { Health } from './types'
import Home, { type StartOptions } from './components/Home'
import Player from './components/Player'
import Library from './components/Library'
import FeedbackForm from './components/FeedbackForm'
import Interview from './components/Interview'
import About from './components/About'
import { IconGear } from './icons'

type Tab = 'home' | 'player' | 'library' | 'feedback' | 'profile' | 'interview' | 'about'

export default function App() {
  const [tab, setTab] = useState<Tab>('home')
  const [health, setHealth] = useState<Health | null>(null)
  const [healthErr, setHealthErr] = useState('')
  const [episodeId, setEpisodeId] = useState<string | null>(null)
  const [startErr, setStartErr] = useState('')
  const [starting, setStarting] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [prefs, setPrefs] = useState<Prefs>(localPrefs())
  const [quiz, setQuiz] = useState(false)
  const [account, setAccount] = useState(false)

  useEffect(() => {
    if (getToken()) {
      api<{ user: User }>('/api/me').then(r => { setUser(r.user); setPrefs(normalize(r.user.prefs)); localStorage.setItem('lm-voice', voiceId(r.user.prefs)) })
        .catch(() => { setToken(null); if (!localPrefs().onboarded) setQuiz(true) })
    } else if (!localPrefs().onboarded) setQuiz(true)
  }, [])

  const [section, setSection] = useState<Section>('narrator')
  useEffect(() => applyAppearance(prefs), [prefs])
  function openSettings(s?: Section) { if (s) setSection(s); setTab('profile') }

  async function updatePrefs(p: Prefs) {
    setPrefs(p)
    const u = await savePrefs(p, user).catch(() => null)
    if (u) setUser(u)
  }
  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    setToken(null); setUser(null)
  }

  useEffect(() => {
    api<Health>('/api/health').then(setHealth).catch(() => setHealthErr('Backend not reachable on :8000. Start it with uvicorn (see README).'))
  }, [])
  useEffect(() => { window.scrollTo(0, 0) }, [tab, episodeId])

  async function start(opts: StartOptions) {
    setStartErr(''); setStarting(true)
    try {
      const r = await api<{ id: string }>('/api/episode', { method: 'POST', body: JSON.stringify(opts) })
      setEpisodeId(r.id); setTab('player')
    } catch (e: any) { setStartErr(e.message) } finally { setStarting(false) }
  }

  function open(id: string) { setEpisodeId(id); setTab('player') }

  const tabs: [Tab, string][] = [['home', 'Listen'], ...(episodeId ? [['player', 'Now playing'] as [Tab, string]] : []), ['interview', 'Interview'], ['library', 'Library'], ['about', 'About']]

  return (
    <div className="app">
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <button className="brand" onClick={() => setTab('home')} aria-label="Loremaster home">
          <span className="sigil" aria-hidden>✦</span>
          <span><span className="brand-name">Loremaster</span><span className="tagline">Canon &amp; Chronicle</span></span>
        </button>
        <nav aria-label="Main">
          {tabs.map(([t, label]) => (
            <button key={t} className={tab === t ? 'active' : ''} aria-current={tab === t ? 'page' : undefined} onClick={() => setTab(t)}>
              {t === 'player' && <span className="live-dot" aria-hidden />}{label}</button>
          ))}
        </nav>
        <div className="status">
          <button className="account-btn" onClick={() => (user ? openSettings('account') : setAccount(true))} aria-label={user ? 'Your preferences' : 'Log in or create an account'}>
            {user ? <><span className="avatar" aria-hidden>{user.name[0]?.toUpperCase()}</span>{user.name.split(' ')[0]}</> : 'Log in'}</button>
          <button className={`settings-btn ${tab === 'profile' ? 'on' : ''}`} onClick={() => openSettings()} aria-label="Settings: narrator voice and story preferences" title="Narrator voice & story preferences"><IconGear /><span>Settings</span></button>
          {health && (health.demo_only
            ? <button className="status-btn warn" onClick={() => openSettings('safety')} title="No API key found: instant stories and the sample episode still play. Click for details."><span className="sdot" aria-hidden />Demo mode</button>
            : <button className="status-btn ok" onClick={() => openSettings('safety')} title={`Live: connected to ${health.model} · voice ${(health as any).audio_engine}. Click for safety & costs.`}
                aria-label={`Live: connected to the AI model ${health.model}. Open safety and transparency.`}><span className="sdot" aria-hidden />Live</button>)}
          {healthErr && <span className="status-btn bad" title={healthErr}><span className="sdot" aria-hidden />Offline</span>}
        </div>
      </header>
      <main id="main">
        {tab === 'home' && <Home health={health} onStart={start} starting={starting} error={startErr} onOpen={open} prefs={prefs} user={user} onQuiz={() => setQuiz(true)} />}
        {tab === 'player' && episodeId && <Player key={episodeId} episodeId={episodeId} health={health} prefs={prefs} onFeedback={() => setTab('feedback')} onNew={() => setTab('home')} />}
        {tab === 'profile' && <Settings user={user} prefs={prefs} health={health} episodeId={episodeId} section={section} onSection={setSection}
          onSave={updatePrefs} onUser={u => { setUser(u); if (!u) setToken(null) }} onLogout={logout} onQuiz={() => setQuiz(true)} onAccount={() => setAccount(true)} />}
        {tab === 'interview' && <Interview prefs={prefs} health={health} />}
        {tab === 'library' && <Library onOpen={open} />}
        {tab === 'about' && <About onListen={() => setTab('home')} onInterview={() => setTab('interview')} onSafety={() => openSettings('safety')} />}
        {tab === 'feedback' && <FeedbackForm episodeId={episodeId} />}
      </main>
      {quiz && <Onboarding initial={prefs} loggedIn={!!user} onSkip={() => { setQuiz(false); updatePrefs({ ...prefs, onboarded: true }) }}
        onDone={p => { setQuiz(false); updatePrefs(p); setTab('home') }} onAccount={() => setAccount(true)} />}
      {account && <AccountModal prefs={prefs} onClose={() => setAccount(false)} onAuthed={u => { setUser(u); if (u.prefs.onboarded) setPrefs(normalize(u.prefs)); else updatePrefs(prefs) }} />}
      <footer>
        <button className="linkish" onClick={() => setTab('about')}>About</button> · <button className="linkish" onClick={() => setTab('feedback')}>Give feedback</button> · <button className="linkish" onClick={() => openSettings('safety')}>Safety &amp; transparency</button> ·
        Evidence from Wikipedia, Wookieepedia and the Warhammer 40k Wiki (CC BY-SA), linked on every claim. Unofficial fan and educational project, not affiliated with Lucasfilm or Games Workshop.
        Narration is AI-generated and fact-checked by AI; grades show how solid each claim is.
      </footer>
    </div>
  )
}
