import { useRef, useState } from 'react'
import { api } from '../api'
import type { Mode } from '../types'
import type { StartOptions } from './Home'

// Resize big phone photos in the browser before upload (≤1600 px, JPEG) — faster, cheaper, private EXIF dropped.
async function toB64(file: File): Promise<{ b64: string; type: string; preview: string }> {
  const img = await createImageBitmap(file)
  const scale = Math.min(1, 1600 / Math.max(img.width, img.height))
  const c = document.createElement('canvas')
  c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale)
  c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
  const url = c.toDataURL('image/jpeg', 0.85)
  return { b64: url.split(',')[1], type: 'image/jpeg', preview: url }
}

export function SnapStory({ onStart, disabled }: { onStart: (o: StartOptions) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<any>(null)
  const [preview, setPreview] = useState('')

  async function onFile(f?: File | null) {
    if (!f) return
    setErr(''); setRes(null); setBusy(true)
    try {
      const { b64, type, preview } = await toB64(f)
      setPreview(preview)
      setRes(await api('/api/snap', { method: 'POST', body: JSON.stringify({ image_b64: b64, media_type: type }) }))
    } catch (e: any) { setErr(e.message || 'Could not read that photo.') } finally { setBusy(false); if (input.current) input.current.value = '' }
  }

  const id = res?.id
  return (
    <section className="discover-card snap">
      <div className="dc-head"><span className="dc-icon" aria-hidden>📸</span><div><h3>Snap &amp; Story</h3><p className="muted small">Photograph a museum piece, a statue, a coin, a book cover, a 40K mini… and hear its story.</p></div></div>
      <input ref={input} type="file" accept="image/*" capture="environment" hidden onChange={e => onFile(e.target.files?.[0])} />
      {!res && <button className="primary" disabled={busy || disabled} onClick={() => input.current?.click()}>{busy ? 'Looking closely…' : 'Take or upload a photo'}</button>}
      {err && <p className="error">{err}</p>}
      {res && <div className="snap-result">
        {preview && <img src={preview} alt="Your photo" />}
        <div>
          <p className="eyebrow">{id.confidence === 'high' ? 'This looks like' : id.confidence === 'medium' ? 'This is probably' : 'This might be'}</p>
          <h4>{id.what}</h4>
          {id.visible_clues?.length > 0 && <p className="muted small">Clues: {id.visible_clues.join(' · ')}</p>}
          {id.alternatives?.length > 0 && <p className="muted small">Could also be: {id.alternatives.join(' · ')}</p>}
          {res.allowed ? <>
            <p className="serif hook">{id.hook || id.story_topic}</p>
            <div className="row">
              <button className="primary" onClick={() => onStart({ topic: id.story_topic, mode: id.mode as Mode, minutes: 10 })}>✦ Tell me this story (~30 s)</button>
              {res.instant && <button className="ghost" onClick={() => onStart({ instant_id: res.instant.id, mode: res.instant.thread.mode, minutes: 10 })}>⚡ Play “{res.instant.title}” now</button>}
            </div>
          </> : <p className="error">{id.reason || 'I can’t make a story from that one.'}</p>}
          <button className="linkish" onClick={() => { setRes(null); setPreview(''); input.current?.click() }}>Try another photo</button>
        </div>
      </div>}
    </section>
  )
}

export function Concierge({ onStart, disabled }: { onStart: (o: StartOptions) => void; disabled?: boolean }) {
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [reply, setReply] = useState<any>(null)
  const [err, setErr] = useState('')
  async function ask(e: React.FormEvent) {
    e.preventDefault(); if (!msg.trim()) return
    setBusy(true); setErr('')
    try { setReply(await api('/api/concierge', { method: 'POST', body: JSON.stringify({ message: msg.trim() }) })) } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <section className="discover-card concierge">
      <div className="dc-head"><span className="dc-icon" aria-hidden>💬</span><div><h3>What are you in the mood for?</h3><p className="muted small">Tell the concierge your time and interests; it picks from the shelf.</p></div></div>
      <form className="dc-form" onSubmit={ask}>
        <input value={msg} onChange={e => setMsg(e.target.value)} maxLength={300} disabled={disabled} placeholder="e.g. “20 minutes on the train, I love sieges and Byzantium”" aria-label="What are you in the mood for?" />
        <button className="primary" disabled={busy || !msg.trim() || disabled}>{busy ? '…' : 'Suggest'}</button>
      </form>
      {err && <p className="error">{err}</p>}
      {reply && <div className="concierge-reply">
        <p className="serif">{reply.message}</p>
        <div className="picks">{reply.picks.map((p: any) => (
          <button key={p.story.id} className="pick" onClick={() => onStart({ instant_id: p.story.id, mode: p.story.thread.mode, minutes: 10 })}>
            <b>⚡ {p.story.thread.title}</b><span>{p.why}</span></button>))}</div>
        {reply.live_idea && <button className="ghost" onClick={() => onStart({ topic: reply.live_idea, mode: 'history', minutes: 10 })}>✦ Write it live: “{reply.live_idea}”</button>}
      </div>}
    </section>
  )
}
