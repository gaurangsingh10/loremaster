// One shared "voice sample" player: any button that plays a sample toggles it (click again to pause),
// and starting a new sample stops the previous one.
import { API } from './api'

let current: HTMLAudioElement | null = null
let currentVoice = ''
const listeners = new Set<() => void>()
const notify = () => listeners.forEach(l => l())

export function sampleState() { return { playing: !!current && !current.paused, voice: currentVoice } }
export function onSampleChange(l: () => void) { listeners.add(l); return () => { listeners.delete(l) } }
export function stopSample() { current?.pause(); current = null; currentVoice = ''; notify() }

/** Toggle: same voice playing -> pause it; otherwise play this voice's sample. */
export function toggleSample(voice: string) {
  if (current && currentVoice === voice && !current.paused) { stopSample(); return }
  current?.pause()
  const a = new Audio(`${API}/api/voice-sample/${voice}`)
  current = a; currentVoice = voice
  a.onended = () => { if (current === a) { current = null; currentVoice = ''; notify() } }
  a.onplaying = notify
  a.play().catch(() => { if (current === a) { current = null; currentVoice = ''; notify() } })
  notify()
}
/** Play (never toggles off): used when the listener picks a different option. */
export function playSample(voice: string) { if (!(current && currentVoice === voice && !current.paused)) toggleSample(voice) }
