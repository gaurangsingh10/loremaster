// Narration player: plays a chapter as a playlist of paragraph-sized audio files rendered by the backend
// (Kokoro neural voice, or the OS voice), prefetching the next segment. Falls back to the browser voice.
//
// Seeking across a playlist: each segment's duration starts as an estimate from its text length and is replaced
// by the real duration as soon as that audio file's metadata loads (the speaking rate learned from real segments
// also sharpens the remaining estimates). So the scrubber is approximate for a moment, then exact.
import { API } from './api'
import { BrowserVoice } from './speech'

export interface Segment { index: number; chars: number; paras: number[] }
export interface PlayerState {
  playing: boolean; loading: boolean; segment: number; total: number; engine: string; error: string; ended: boolean
  position: number; duration: number; marks: number[]   // seconds; marks = start time of each section
}

function splitParas(narration: string) { return narration.split(/\n+/).filter(p => p.trim()).map(p => p.replace(/\s*\[c\d+\]/g, '').trim()) }

export class ChapterPlayer {
  private audio = new Audio()
  private next: HTMLAudioElement | null = null
  private browser = new BrowserVoice()
  private segs: Segment[] = []
  private paras: string[] = []
  private eid = ''
  private chapter = 0
  private voice = 'george'
  private token = 0
  private real: (number | null)[] = []      // measured durations (s) per segment
  private secPerChar = 1 / 14.5             // learned from real segments; ~150 wpm to start
  private pendingOffset = 0                 // seek offset to apply once the segment's audio is ready
  private browserStart = 0                  // wall-clock start of the current browser-voice segment
  state: PlayerState = { playing: false, loading: false, segment: 0, total: 0, engine: '', error: '', ended: false, position: 0, duration: 0, marks: [] }
  rate = 1
  onChange: (s: PlayerState) => void = () => {}

  constructor() {
    this.audio.preload = 'auto'
    this.audio.addEventListener('ended', () => this.advance())
    this.audio.addEventListener('error', () => { if (this.state.playing && this.state.engine !== 'browser') this.useBrowser('Audio file failed; using browser voice.') })
    this.audio.addEventListener('playing', () => this.set({ loading: false }))
    this.audio.addEventListener('waiting', () => this.set({ loading: true }))
    this.audio.addEventListener('loadedmetadata', () => {
      const i = this.state.segment
      if (isFinite(this.audio.duration) && this.audio.duration > 0) this.learn(i, this.audio.duration)
      if (this.pendingOffset > 0) { this.audio.currentTime = Math.min(this.pendingOffset, Math.max(0, this.audio.duration - 0.3)); this.pendingOffset = 0 }
      this.tick()
    })
    this.audio.addEventListener('timeupdate', () => this.tick())
    setInterval(() => { if (this.state.playing && this.state.engine === 'browser') this.tick() }, 500)
  }

  // ---------------------------------------------------------------- timing model
  private learn(i: number, dur: number) {
    if (this.real[i] === dur) return
    this.real[i] = dur
    const known = this.segs.filter((_, k) => this.real[k]).map(s => s.index)
    const chars = known.reduce((a, k) => a + this.segs[k].chars, 0)
    const secs = known.reduce((a, k) => a + (this.real[k] ?? 0), 0)
    if (chars > 0) this.secPerChar = secs / chars
  }
  private segDur(i: number) { return this.real[i] ?? this.segs[i].chars * this.secPerChar }
  private starts(): number[] { const out: number[] = []; let t = 0; for (let i = 0; i < this.segs.length; i++) { out.push(t); t += this.segDur(i) } return out }
  private within(): number {
    if (this.state.engine === 'browser') return this.state.playing ? Math.min((Date.now() - this.browserStart) / 1000 * this.rate, this.segDur(this.state.segment)) : 0
    return this.audio.currentTime || this.pendingOffset || 0
  }
  private tick() {
    if (!this.segs.length) return
    const marks = this.starts()
    const duration = marks[marks.length - 1] + this.segDur(this.segs.length - 1)
    const position = this.state.ended ? duration : (marks[this.state.segment] ?? 0) + this.within()
    this.set({ position, duration, marks })
  }

  private set(p: Partial<PlayerState>) { this.state = { ...this.state, ...p }; this.onChange(this.state) }
  private url(i: number) { return `${API}/api/audio/${this.eid}/${this.chapter}/${i}?voice=${this.voice}` }

  async load(eid: string, chapter: number, narration: string, voice: string) {
    this.stop()
    const tok = ++this.token
    this.eid = eid; this.chapter = chapter; this.voice = voice
    this.paras = splitParas(narration)
    this.real = []
    this.set({ playing: false, loading: false, segment: 0, total: 0, error: '', ended: false, position: 0, duration: 0, marks: [] })
    try {
      const r = await fetch(`${API}/api/audio/${eid}/${chapter}/manifest?voice=${voice}`)
      if (tok !== this.token) return
      if (!r.ok) throw new Error()
      const m = await r.json()
      if (m.engine === 'none') throw new Error()
      this.segs = m.segments
      this.set({ total: this.segs.length, engine: m.engine })
    } catch {
      if (tok !== this.token) return
      this.segs = this.paras.map((_, i) => ({ index: i, chars: this.paras[i].length, paras: [i] }))
      this.set({ total: this.segs.length, engine: 'browser' })
    }
    this.real = this.segs.map(() => null)
    this.tick()
  }

  paraIndices(seg = this.state.segment): number[] { return this.segs[seg]?.paras ?? [] }

  play() {
    if (!this.segs.length) return
    if (this.state.ended) { this.set({ segment: 0, ended: false }); this.pendingOffset = 0 }
    this.set({ playing: true, error: '' })
    this.playSegment(this.state.segment, this.pendingOffset || this.audio.currentTime || 0)
  }

  private playSegment(i: number, offset = 0) {
    this.set({ segment: i })
    if (this.state.engine === 'browser') {
      const text = this.paraIndices(i).map(p => this.paras[p]).join(' ')
      this.browser.rate = this.rate
      this.browserStart = Date.now()
      this.browser.speak(text, () => this.advance(), msg => this.set({ error: msg, playing: false }))
      return
    }
    const src = this.url(i)
    const same = this.audio.src && this.audio.src.endsWith(src.replace(API, '')) && this.audio.readyState > 0
    if (!same) {
      this.audio.src = this.next && this.next.src === src ? this.next.src : src
      this.pendingOffset = offset
    } else if (offset) {
      this.audio.currentTime = offset
    }
    this.audio.playbackRate = this.rate
    this.set({ loading: true })
    this.audio.play().catch(err => {
      if (err?.name === 'NotAllowedError') this.set({ playing: false, loading: false, error: 'Tap play to start audio.' })
      else if (err?.name !== 'AbortError') this.useBrowser('Audio unavailable; using browser voice.')
    })
    if (i + 1 < this.segs.length) { this.next = new Audio(this.url(i + 1)); this.next.preload = 'auto'
      this.next.addEventListener('loadedmetadata', () => { const n = this.next; if (n && isFinite(n.duration)) { this.learn(i + 1, n.duration); this.tick() } }) }
  }

  private advance() {
    if (!this.state.playing) return
    const n = this.state.segment + 1
    if (n >= this.segs.length) { this.set({ playing: false, ended: true }); this.tick(); return }
    this.playSegment(n, 0)
  }

  private useBrowser(msg: string) {
    this.audio.pause()
    this.segs = this.paras.map((_, i) => ({ index: i, chars: this.paras[i].length, paras: [i] }))
    this.real = this.segs.map(() => null)
    this.set({ engine: 'browser', error: msg, total: this.segs.length, segment: Math.min(this.state.segment, this.segs.length - 1) })
    if (this.state.playing) this.playSegment(this.state.segment)
  }

  pause() { this.set({ playing: false, loading: false }); this.audio.pause(); this.browser.stop(); this.tick() }
  stop() { this.pause(); this.audio.removeAttribute('src'); this.next = null; this.pendingOffset = 0 }
  toggle() { this.state.playing ? this.pause() : this.play() }

  /** Jump to an absolute time (seconds) in the chapter: the scrubber. */
  seekTo(t: number) {
    if (!this.segs.length) return
    const marks = this.starts()
    let i = marks.length - 1
    while (i > 0 && marks[i] > t) i--
    const offset = Math.max(0, t - marks[i])
    const wasPlaying = this.state.playing
    this.set({ ended: false })
    if (i !== this.state.segment || this.state.engine === 'browser') {
      this.audio.pause(); this.browser.stop()
      this.set({ segment: i })
      if (wasPlaying) this.playSegment(i, offset)
      else { this.pendingOffset = offset; if (this.state.engine !== 'browser') { this.audio.src = this.url(i) } }
    } else if (this.audio.readyState > 0) {
      this.audio.currentTime = Math.min(offset, Math.max(0, this.audio.duration - 0.3))
    } else {
      this.pendingOffset = offset
    }
    this.tick()
  }
  skipSeconds(delta: number) { this.seekTo(Math.max(0, Math.min(this.state.duration - 0.5, this.state.position + delta))) }
  skip(delta: number) {  // previous/next section
    const i = Math.max(0, Math.min(this.segs.length - 1, this.state.segment + delta))
    this.seekTo(this.starts()[i] + 0.01)
  }
  seekToPara(para: number) {
    const i = this.segs.findIndex(s => s.paras.includes(para))
    if (i >= 0) { this.seekTo(this.starts()[i] + 0.01); if (!this.state.playing) this.play() }
  }
  setRate(r: number) { this.rate = r; this.audio.playbackRate = r; this.browser.rate = r; if (this.state.playing && this.state.engine === 'browser') this.skip(0) }
}

export function fmtTime(s: number) {
  if (!isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
