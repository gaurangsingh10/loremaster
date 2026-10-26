// Fire-and-forget interaction logging (impact evidence: curiosity metrics on the "How it works" page).
import { API, getToken } from './api'
import { localPrefs } from './prefs'

export function logEvent(kind: string, episode_id: string, chapter: number | null = null, data: Record<string, unknown> = {}) {
  if (!localPrefs().usage_stats) return   // the listener opted out in Settings → Privacy
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = getToken(); if (t) headers.Authorization = `Bearer ${t}`
  fetch(`${API}/api/events`, { method: 'POST', headers, body: JSON.stringify({ kind, episode_id, chapter, data }), keepalive: true }).catch(() => {})
}
