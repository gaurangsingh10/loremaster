import { useEffect, useState } from 'react'
import { api, fmtUsd, post } from '../api'
import type { Health } from '../types'

const DEMO_TITLES: Record<string, string> = {
  invented_lore: 'Invented-lore catcher', poisoned_page: 'Poisoned wiki page', budget_cap: 'Budget cap', harmful_history: 'Harmful-history guard',
}

export default function Curtain({ episodeId, health }: { episodeId: string | null; health: Health | null }) {
  const [runs, setRuns] = useState<any[]>([])
  const [auditRows, setAudit] = useState<any[]>([])
  const [demos, setDemos] = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, any>>({})
  const [busy, setBusy] = useState('')
  const [curiosity, setCuriosity] = useState<any>(null)

  useEffect(() => {
    api('/api/usage/latest?limit=12').then(r => setRuns(r.runs.reverse())).catch(() => {})
    api('/api/safety/demos').then(r => setDemos(r.demos)).catch(() => {})
    api('/api/events/summary').then(setCuriosity).catch(() => {})
    if (episodeId && episodeId !== 'demo') api(`/api/audit/${episodeId}`).then(r => setAudit(r.entries)).catch(() => {})
  }, [episodeId])

  async function run(demo: string, defenses: 'all' | 'none') {
    const key = `${demo}:${defenses}`
    setBusy(key)
    try { const r = await post(`/api/safety/run/${demo}?defenses=${defenses}`); setResults(x => ({ ...x, [key]: r })) }
    catch (e: any) { setResults(x => ({ ...x, [key]: { summary: e.message, blocked: false } })) }
    setBusy('')
  }

  return (
    <div className="curtain">
      <h2>Behind the curtain</h2>
      <p className="lede">What it costs, what the agents did, and the defenses that keep it honest. Every number here comes from real API usage.</p>

      {curiosity && <section className="card">
        <h3>Curiosity metrics (from real listening sessions)</h3>
        <div className="curio">
          <div><b>{curiosity.episodes}</b><span>episodes with activity</span></div>
          <div><b>{curiosity.claim_taps_per_episode}</b><span>“Is that true?” taps per episode</span></div>
          <div><b>{curiosity.questions_asked}</b><span>questions asked the narrator</span></div>
          <div><b>{curiosity.myth_or_fact_accuracy === null ? '–' : Math.round(curiosity.myth_or_fact_accuracy * 100) + '%'}</b><span>Myth or Fact? correct</span></div>
          <div><b>{curiosity.callit_accuracy === null ? '–' : Math.round(curiosity.callit_accuracy * 100) + '%'}</b><span>Call it correct</span></div>
          <div><b>{curiosity.minutes_listened}</b><span>minutes listened</span></div>
        </div>
        <p className="muted small">Logged anonymously to output/interaction_log.json; used as impact evidence.</p>
      </section>}

      <section className="card">
        <h3>Recent runs: tokens &amp; cost (gpt-6-luna)</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Episode</th><th>Thread</th><th>Min</th><th>Ch.</th><th>Status</th><th>Input</th><th>Cached</th><th>Output</th><th>Cost</th></tr></thead>
          <tbody>{runs.map((r, i) => {
            const t = (r.agents ?? []).reduce((s: any, a: any) => ({ i: s.i + a.input_tokens, c: s.c + a.cached_tokens, o: s.o + a.output_tokens }), { i: 0, c: 0, o: 0 })
            return <tr key={i}><td>{r.episode_id}</td><td>{r.thread}</td><td>{r.minutes}</td><td>{r.chapters_done}/{r.total_chapters}</td><td>{r.status}</td>
              <td>{t.i.toLocaleString()}</td><td>{t.c.toLocaleString()}</td><td>{t.o.toLocaleString()}</td><td>{fmtUsd(r.total_usd)}</td></tr>
          })}</tbody>
        </table></div>
        {!runs.length && <p className="muted">No runs logged yet.</p>}
      </section>

      <section className="card">
        <h3>Safety Lab</h3>
        <p className="muted">Run each attack with defenses ON and OFF. ON should block it; OFF shows why the defense exists.{health?.demo_only ? ' (Needs an API key; recorded results are in output/safety_results.md.)' : ''}</p>
        <div className="lab">
          {Object.entries(demos).map(([id, desc]) => (
            <div key={id} className="lab-card">
              <h4>{DEMO_TITLES[id] ?? id}</h4><p className="muted">{desc}</p>
              <div className="row">
                <button disabled={!!busy || health?.demo_only} onClick={() => run(id, 'all')}>{busy === `${id}:all` ? 'Running…' : 'Run · defenses ON'}</button>
                <button className="ghost" disabled={!!busy || health?.demo_only} onClick={() => run(id, 'none')}>{busy === `${id}:none` ? 'Running…' : 'Run · defenses OFF'}</button>
              </div>
              {(['all', 'none'] as const).map(d => results[`${id}:${d}`] && (
                <div key={d} className={`result ${results[`${id}:${d}`].blocked ? 'ok' : 'bad'}`}>
                  <b>{d === 'all' ? 'ON' : 'OFF'}: {results[`${id}:${d}`].blocked ? 'blocked ✓' : 'got through ✗'}</b>
                  <p>{results[`${id}:${d}`].summary}</p>
                  {results[`${id}:${d}`].claims && <ul>{results[`${id}:${d}`].claims.map((c: any) => <li key={c.id}><b>{c.grade}</b> {c.text}</li>)}</ul>}
                  {results[`${id}:${d}`].cases && <ul>{results[`${id}:${d}`].cases.map((c: any) => <li key={c.topic}>{c.allowed ? 'allowed' : 'refused'} ({c.layer}) · {c.topic}</li>)}</ul>}
                  {results[`${id}:${d}`].quarantined?.length > 0 && <details><summary>Quarantined by code ({results[`${id}:${d}`].quarantined.length})</summary><ul>{results[`${id}:${d}`].quarantined.map((q: string, i: number) => <li key={i}>{q}</li>)}</ul></details>}
                  {results[`${id}:${d}`].narration_excerpt && <details><summary>Narration excerpt</summary><p className="small">{results[`${id}:${d}`].narration_excerpt}</p></details>}
                  {results[`${id}:${d}`].cost_usd !== undefined && <small className="muted">cost {fmtUsd(results[`${id}:${d}`].cost_usd)}</small>}
                </div>))}
            </div>))}
        </div>
      </section>

      <section className="card">
        <h3>Audit trail {episodeId && episodeId !== 'demo' ? `· episode ${episodeId}` : ''}</h3>
        {!auditRows.length && <p className="muted">Play a live episode to see every agent step here (also saved to output/audit_trail.json).</p>}
        <div className="table-wrap"><table className="audit">
          <tbody>{auditRows.map((a, i) => <tr key={i}><td>{a.ts?.slice(11, 19)}</td><td>{a.agent}</td><td>{a.event}</td><td>{a.tool ?? ''}</td><td>{a.args ?? a.result ?? a.stop_reason ?? ''}</td><td>{a.tokens ? fmtUsd(a.tokens.cost_usd) : ''}</td></tr>)}</tbody>
        </table></div>
      </section>
    </div>
  )
}
