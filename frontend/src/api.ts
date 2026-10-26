const env = (import.meta as any).env?.VITE_API as string | undefined
export const API = env ?? (location.port === '5173' ? 'http://localhost:8000' : '')

export const getToken = () => localStorage.getItem('lm-token')
export const setToken = (t: string | null) => (t ? localStorage.setItem('lm-token', t) : localStorage.removeItem('lm-token'))

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  // Settings → Privacy: when usage stats are off, ask the server not to log this call either
  try { if (JSON.parse(localStorage.getItem('lm-prefs') || '{}').usage_stats === false) headers['X-Usage-Stats'] = 'off' } catch { /* ignore */ }
  const r = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init?.headers as any) } })
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}
export const post = <T = any>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const GRADE_INFO: Record<string, { color: string; label: string; blurb: string }> = {
  Documented: { color: '#7fb77e', label: 'Documented', blurb: 'The sources state it plainly.' },
  Canon: { color: '#7fb77e', label: 'Canon', blurb: 'Stated in current official lore.' },
  Debated: { color: '#e0b04f', label: 'Debated', blurb: 'Sources disagree or only partly support it.' },
  Conflicting: { color: '#e0b04f', label: 'Conflicting', blurb: 'Official sources contradict each other.' },
  Legend: { color: '#c98bdb', label: 'Legend', blurb: 'A great story the sources treat as legend.' },
  Legends: { color: '#c98bdb', label: 'Legends', blurb: 'Only in the old Expanded Universe (non-canon).' },
  'Fan theory': { color: '#8fb3e8', label: 'Fan theory', blurb: 'Popular fan interpretation, not confirmed.' },
  Interpretation: { color: '#9a9a9a', label: 'Interpretation', blurb: "The narrator's framing or a history-to-fiction parallel: an opinion, not a fact." },
  Unsupported: { color: '#e06c5f', label: 'Unsupported', blurb: 'No source we found says this.' },
}
export const AGENTS = [
  { id: 'guardian', name: 'Guardian', role: 'screens requests', glyph: '⛨' },
  { id: 'showrunner', name: 'Showrunner', role: 'plans the arc', glyph: '✦' },
  { id: 'researcher', name: 'Researcher', role: 'finds evidence', glyph: '⌕' },
  { id: 'storyteller', name: 'Storyteller', role: 'narrates', glyph: '❦' },
  { id: 'skeptic', name: 'Skeptic', role: 'grades every claim', glyph: '⚖' },
  { id: 'librarian', name: 'Librarian', role: 'further reading', glyph: '❧' },
]
export const fmtUsd = (x: number) => (x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(3)}`)
