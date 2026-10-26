// Listening preferences: saved to the account when logged in, otherwise kept in this browser.
import { api } from './api'
import type { Thread } from './types'

export type Topic = 'crossover' | 'history' | 'science' | 'technology' | 'politics' | 'lore'
export const TOPICS: { id: Topic; label: string; glyph: string; sub: string }[] = [
  { id: 'crossover', label: 'History × lore', glyph: '⚖✷', sub: 'Rome → Galactic Empire' },
  { id: 'history', label: 'Real history', glyph: '🏛', sub: 'Myths put on trial' },
  { id: 'science', label: 'Science', glyph: '⚛', sub: 'How we know, and the myths' },
  { id: 'technology', label: 'Technology', glyph: '⚙', sub: 'Inventions that changed everything' },
  { id: 'politics', label: 'Politics & ideas', glyph: '⚑', sub: 'How power works, all sides heard' },
  { id: 'lore', label: 'Fictional lore', glyph: '☩', sub: 'Canon vs. Legends' },
]
export interface Prefs {
  voice_gender: 'male' | 'female'; accent: 'uk' | 'us'; tone: 'deep' | 'natural'; speed: number
  interests: Topic[]   // several story types at once; empty = surprise me (a mix)
  content: Topic | 'mix'   // legacy single choice (= interests[0]), kept for older saved settings
  worlds: string[]; minutes: 10 | 20 | 40; persona: string; onboarded: boolean
  theme: 'dark' | 'light' | 'system'; text_size: 'normal' | 'large' | 'xlarge'; reduce_motion: boolean
  auto_read: boolean; autoplay_next: boolean; usage_stats: boolean
}
export interface User { id: number; email: string; name: string; prefs: Prefs }

export const DEFAULT_PREFS: Prefs = { voice_gender: 'male', accent: 'uk', tone: 'deep', speed: 1, interests: ['crossover'], content: 'crossover', worlds: [], minutes: 20, persona: '', onboarded: false,
  theme: 'dark', text_size: 'normal', reduce_motion: false, auto_read: true, autoplay_next: true, usage_stats: true }
export const voiceId = (p: Prefs) => `${p.voice_gender}-${p.accent}-${p.tone}`

// Older saved settings have only `content`; turn that into the interests list.
export function normalize(p: Partial<Prefs>): Prefs {
  const q = { ...DEFAULT_PREFS, ...p } as Prefs
  if (!Array.isArray(p.interests)) q.interests = p.content && p.content !== 'mix' ? [p.content] : p.content === 'mix' ? [] : DEFAULT_PREFS.interests
  // science / technology / politics used to be "worlds"; they're story types now
  const moved = q.worlds.filter(w => w === 'science' || w === 'technology' || w === 'politics') as Topic[]
  if (moved.length) { q.interests = [...new Set([...q.interests, ...moved])]; q.worlds = q.worlds.filter(w => !moved.includes(w as Topic)) }
  q.content = q.interests[0] ?? 'mix'
  return q
}
export const likes = (p: Prefs, t: Topic) => p.interests.includes(t)
export function localPrefs(): Prefs {
  try { return normalize(JSON.parse(localStorage.getItem('lm-prefs') || '{}')) } catch { return DEFAULT_PREFS }
}
// Theme, text size and motion live on <html> so the whole app (and the player dock) follows them.
const darkQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null
export function applyAppearance(p: Prefs) {
  const el = document.documentElement
  const theme = p.theme === 'system' ? (darkQuery?.matches === false ? 'light' : 'dark') : p.theme
  el.dataset.theme = theme
  el.dataset.textSize = p.text_size
  el.dataset.reduceMotion = String(p.reduce_motion)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f5efe2' : '#0b1020')
}
darkQuery?.addEventListener('change', () => { const p = localPrefs(); if (p.theme === 'system') applyAppearance(p) })

export async function savePrefs(p: Prefs, user: User | null): Promise<User | null> {
  p = normalize(p)
  localStorage.setItem('lm-prefs', JSON.stringify(p))
  localStorage.setItem('lm-voice', voiceId(p))
  if (!user) return null
  const r = await api<{ user: User }>('/api/me/prefs', { method: 'PUT', body: JSON.stringify(p) })
  return r.user
}

export const WORLDS = [
  { id: 'warhammer40k', label: 'Warhammer 40K', glyph: '☩' },
  { id: 'star_wars', label: 'Star Wars', glyph: '✷' },
  { id: 'rome', label: 'Rome & Byzantium', glyph: '🏛' },
  { id: 'medieval', label: 'Crusades & Middle Ages', glyph: '⚔' },
  { id: 'myths', label: 'Myths & mysteries', glyph: '❓' },
  { id: 'modern', label: 'Modern history', glyph: '🕰' },
]
export const genreOf = (t: Thread) => t.genre || (t.mode === 'lore' ? 'lore' : 'history')

/** Which worlds a story touches (for recommendations). */
export function storyWorlds(t: Thread): string[] {
  const s = `${t.title} ${t.hook} ${t.era}`.toLowerCase()
  const w = t.packs.filter(p => p !== 'history')
  const g = genreOf(t); if (['science', 'technology', 'politics'].includes(g) && !w.includes(g)) w.push(g)
  if (/rome|roman|caesar|nero|byzant|constantinople|varangian|sparta|alexandria/.test(s)) w.push('rome')
  if (/templar|crusade|inquisition|medieval|mongol|khan|visigoth|castil/.test(s)) w.push('medieval')
  if (/myth|legend|did |really|who really|fiddle|1177|collapse/.test(s)) w.push('myths')
  if (/vietnam|manhattan|1942|texas/.test(s)) w.push('modern')
  return w
}
export function scoreStory(t: Thread, p: Prefs): number {
  let s = storyWorlds(t).filter(w => p.worlds.includes(w)).length * 2
  const g = genreOf(t)
  if (likes(p, 'crossover') && t.mode === 'crossover') s += 2
  if (likes(p, 'lore') && g === 'lore') s += 2
  if (likes(p, 'history') && g === 'history' && t.mode === 'history') s += 2
  if ((['science', 'technology', 'politics'] as Topic[]).some(x => likes(p, x) && g === x)) s += 3
  return s
}
export function personaFor(p: Prefs): { name: string; blurb: string } {
  const w = p.worlds
  if (p.interests.length > 3) return { name: 'The Polymath', blurb: 'Emperors, inventors, senators and Sith Lords: you want all of it, each claim graded.' }
  if (w.includes('warhammer40k') && (likes(p, 'lore') || likes(p, 'crossover'))) return { name: 'The Lord Inquisitor', blurb: 'You want the grimdark, and the real history that forged it. Heresy will be graded.' }
  if (w.includes('star_wars')) return { name: 'The Jedi Archivist', blurb: 'Canon or Legends? You care, and so do we. Expect Senate politics with Roman roots.' }
  if (likes(p, 'science') || (w.includes('science') && !w.includes('warhammer40k'))) return { name: 'The Curious Experimentalist', blurb: 'You want to know how we know, and which famous discovery stories are really myths.' }
  if (likes(p, 'technology') || w.includes('technology')) return { name: 'The Tinkerer', blurb: 'Telegraph wires, war of the currents, lone-genius myths: the real story of how things got invented.' }
  if (likes(p, 'politics') || w.includes('politics')) return { name: 'The Statesman', blurb: 'How power is built, split and argued over, with every side heard and every claim graded.' }
  if (likes(p, 'history') && w.includes('myths')) return { name: 'The Myth-Buster', blurb: 'You love a good story, and love it more when you know which bits are legend.' }
  if (likes(p, 'history')) return { name: 'The Chronicler', blurb: 'Sweeping real history, every claim sourced. Long-form is your natural habitat.' }
  return { name: 'The Wandering Scholar', blurb: 'A little of everything: emperors, Sith Lords and the line between them.' }
}
