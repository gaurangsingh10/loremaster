import { useState } from 'react'
import { post } from '../api'

export default function FeedbackForm({ episodeId }: { episodeId: string | null }) {
  const [rating, setRating] = useState(0)
  const [minutes, setMinutes] = useState('')
  const [tomorrow, setTomorrow] = useState<boolean | null>(null)
  const [fav, setFav] = useState('')
  const [quote, setQuote] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [sent, setSent] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!rating) { setErr('Pick a rating first.'); return }
    try {
      await post('/api/feedback', { episode_id: episodeId, rating, minutes_listened: minutes ? Number(minutes) : null, listen_tomorrow: tomorrow, favorite_moment: fav, quote, name, role })
      setSent(true)
    } catch (e: any) { setErr(e.message) }
  }

  if (sent) return <div className="feedback card"><h2>Thank you!</h2><p className="lede">Your feedback is saved. It helps make Loremaster something people actually want on their commute.</p></div>
  return (
    <form className="feedback card" onSubmit={submit}>
      <h2>How was the episode?</h2>
      <p className="lede">Takes one minute. Your quote might end up in the project report (we'll use only the name or role you give).</p>
      <label>Overall rating</label>
      <div className="stars">{[1, 2, 3, 4, 5].map(n => <button type="button" key={n} className={n <= rating ? 'on' : ''} onClick={() => setRating(n)}>★</button>)}</div>
      <label>Minutes you listened<input type="number" min={0} max={120} value={minutes} onChange={e => setMinutes(e.target.value)} /></label>
      <label>Would you listen to another episode tomorrow?</label>
      <div className="seg">{[['Yes', true], ['No', false]].map(([l, v]) => <button type="button" key={String(l)} className={tomorrow === v ? 'on' : ''} onClick={() => setTomorrow(v as boolean)}>{l as string}</button>)}</div>
      <label>Favorite moment<input value={fav} onChange={e => setFav(e.target.value)} placeholder="The bit you'd repeat to a friend" /></label>
      <label>A quote we can use<textarea value={quote} onChange={e => setQuote(e.target.value)} rows={3} placeholder="What would you tell a friend about this?" /></label>
      <div className="row"><label>Name (optional)<input value={name} onChange={e => setName(e.target.value)} /></label>
        <label>Role (optional)<input value={role} onChange={e => setRole(e.target.value)} placeholder="e.g. SOM MBA, Metro-North commuter, 40K fan" /></label></div>
      {err && <p className="error">{err}</p>}
      <button className="primary">Send feedback</button>
    </form>
  )
}
