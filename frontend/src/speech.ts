// Fallback voice: the browser's Web Speech API (only used when the backend has no audio engine).
// Hardened per the accessibility review: utterances are kept alive (Chrome GC bug), a generation token ignores
// callbacks from cancelled utterances, resume() un-sticks Chrome, voices are cached on 'voiceschanged',
// and speak() is deferred after cancel().

let cachedVoice: SpeechSynthesisVoice | null = null

function chooseVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices() ?? []
  const prefs = ['Daniel', 'Google UK English Male', 'Arthur', 'Oliver', 'Microsoft Ryan', 'Alex', 'Google US English', 'Samantha']
  for (const p of prefs) {
    const v = voices.find(v => v.name.includes(p))
    if (v) return v
  }
  return voices.find(v => v.lang.startsWith('en')) ?? null
}
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  cachedVoice = chooseVoice()
  window.speechSynthesis.addEventListener?.('voiceschanged', () => { cachedVoice = chooseVoice() })
}

export function speechSupported() { return typeof window !== 'undefined' && 'speechSynthesis' in window }

export class BrowserVoice {
  private gen = 0
  private current: SpeechSynthesisUtterance | null = null
  rate = 1

  speak(text: string, onEnd: () => void, onError: (msg: string) => void) {
    if (!speechSupported()) { onError('This browser has no speech engine.'); return }
    const gen = ++this.gen
    const synth = window.speechSynthesis
    synth.cancel()
    setTimeout(() => {
      if (gen !== this.gen) return
      const u = new SpeechSynthesisUtterance(text)
      if (cachedVoice) u.voice = cachedVoice
      u.rate = this.rate
      u.pitch = 0.9
      u.onend = () => { if (gen === this.gen) onEnd() }
      u.onerror = (e: SpeechSynthesisErrorEvent) => {
        if (gen !== this.gen || e.error === 'interrupted' || e.error === 'canceled') return
        onError(`Browser voice error: ${e.error}`)
      }
      this.current = u          // keep a reference so Chrome can't garbage-collect it mid-speech
      synth.resume()            // un-stick Chrome's paused state
      synth.speak(u)
    }, 60)
  }
  stop() { this.gen++; this.current = null; if (speechSupported()) window.speechSynthesis.cancel() }
}
