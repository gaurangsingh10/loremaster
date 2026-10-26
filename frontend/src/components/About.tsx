import { GRADE_INFO } from '../api'
import { coverUrl } from '../covers'

const HISTORY = ['Documented', 'Debated', 'Legend', 'Interpretation', 'Unsupported']
const LORE = ['Canon', 'Legends', 'Conflicting', 'Fan theory']
const MARK: Record<string, string> = { Documented: 'D', Canon: 'C', Debated: '≈', Conflicting: '≠', Legend: 'L', Legends: 'L', 'Fan theory': 'F', Interpretation: 'i', Unsupported: '?' }

export default function About({ onListen, onInterview, onSafety }: { onListen: () => void; onInterview: () => void; onSafety: () => void }) {
  return (
    <div className="about">
      <section className="about-hero">
        <p className="eyebrow">About Loremaster</p>
        <h1>Curiosity you can trust.</h1>
        <p className="lede">Loremaster is an AI storyteller for your commute. It tells long, gripping stories about real history, science, technology
          and politics, and about the lore of Star Wars and Warhammer 40,000. Then it does something no podcast does: it tells you <b>how much of each story is true</b>.</p>
        <div className="row"><button className="primary" onClick={onListen}>▶ Start listening</button><button className="ghost" onClick={onInterview}>🎙 Interview the past</button></div>
      </section>

      <section className="about-idea">
        <img src={coverUrl('texas-law-medieval-spain')} alt="" className="about-pic" />
        <div>
          <p className="eyebrow">The idea</p>
          <h2>It started with a myth I believed</h2>
          <p>I love history, historical fiction and deep fictional lore, and I spend a lot of time on trains. I'd heard, and happily repeated, that Texas divorce law
            "comes from Muslim Spain." When I finally checked, the sources pointed somewhere else: to Visigothic and Castilian law. The Muslim-Spain version is a legend.</p>
          <p>That's the problem with how most of us learn about the past. Podcasts and lecture videos are brilliant, but you can't steer them or stop to ask "wait, is that true?"
            Wikis are accurate, but you can't read them while driving. And AI chatbots will talk about anything, in the same confident voice whether it's fact or legend.
            You walk away "knowing" things that aren't so.</p>
          <p><b>Loremaster keeps the fun of a great story and adds a one-tap answer to "is that true?"</b></p>
        </div>
      </section>

      <section>
        <p className="eyebrow">Why it's worth your commute</p>
        <h2>The value proposition</h2>
        <div className="about-grid">
          <div className="about-card"><span aria-hidden>⚖</span><h3>Every claim is graded</h3><p>Each sentence carries a mark: documented, debated, legend, or fan theory. Tap it to see the evidence and its source. In my tests, a plain AI chatbot presented <b>95%</b> of the claims its sources don't back as plain fact. With Loremaster's grading, only <b>5%</b> slip through unflagged.</p></div>
          <div className="about-card"><span aria-hidden>✦</span><h3>You steer the story</h3><p>10, 20 or 40-minute episodes with a choice at every chapter. Go deeper on the siege, skip the politics, follow the side character. Tomorrow's commute picks up where you left off.</p></div>
          <div className="about-card"><span aria-hidden>🏛→✷</span><h3>The history behind the lore</h3><p>Crossover episodes braid real history into fictional canon: Caesar's Rubicon and Palpatine's emergency powers, the Varangian Guard and the Adeptus Custodes. Two audiences that already overlap.</p></div>
          <div className="about-card"><span aria-hidden>💬</span><h3>Listening that talks back</h3><p>Pause and ask the narrator anything. Make a call before the big reveal. Play Myth or Fact? after each chapter. Interview Caesar himself, with his boasts graded.</p></div>
          <div className="about-card"><span aria-hidden>⚡</span><h3>Instant and nearly free</h3><p>Twenty-one stories start in under a second. A brand-new episode is written live in about 30 seconds for roughly a cent, and the narrator's voice runs on your device.</p></div>
          <div className="about-card"><span aria-hidden>📸</span><h3>Start from the world around you</h3><p>Photograph a statue, a coin or a museum piece, and Loremaster tells you what it probably is, how sure it is, and the story behind it.</p></div>
        </div>
      </section>

      <section className="about-compare card">
        <h3>How it compares</h3>
        <table>
          <thead><tr><th></th><th>Grades every claim</th><th>You steer it</th><th>Ask questions</th><th>History × lore</th></tr></thead>
          <tbody>
            <tr><td>History podcasts &amp; lore YouTube</td><td className="no">✗</td><td className="no">✗</td><td className="no">✗</td><td className="no">✗</td></tr>
            <tr><td>Wikipedia &amp; fan wikis</td><td className="part">sourced</td><td className="no">✗</td><td className="no">✗</td><td className="no">✗</td></tr>
            <tr><td>AI chatbots (voice mode)</td><td className="no">✗</td><td className="part">chat</td><td className="yes">✓</td><td className="part">if asked</td></tr>
            <tr><td>AI podcast generators</td><td className="no">✗</td><td className="no">✗</td><td className="part">some</td><td className="no">✗</td></tr>
            <tr className="us"><td><b>Loremaster</b></td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td></tr>
          </tbody>
        </table>
      </section>

      <section>
        <p className="eyebrow">Reading the marks</p>
        <h2>What the grades mean</h2>
        <div className="about-legend">
          <div><h4>Real history, science &amp; politics</h4>{HISTORY.map(g => <p key={g}><span className="legend-mark" style={{ borderColor: GRADE_INFO[g].color, color: GRADE_INFO[g].color }}>{MARK[g]}</span><b>{g}</b> {GRADE_INFO[g].blurb}</p>)}</div>
          <div><h4>Fictional lore</h4>{LORE.map(g => <p key={g}><span className="legend-mark" style={{ borderColor: GRADE_INFO[g].color, color: GRADE_INFO[g].color }}>{MARK[g]}</span><b>{g}</b> {GRADE_INFO[g].blurb}</p>)}
            <p className="muted small">Star Wars really does have an official "Legends" label for its old Expanded Universe, and 40K contradicts itself on purpose. Lore fans argue about exactly this.</p></div>
        </div>
      </section>

      <section>
        <p className="eyebrow">Under the hood</p>
        <h2>How a story gets made honestly</h2>
        <ol className="about-steps">
          <li><b>A Guardian</b> screens your request: no atrocity denial, no campaigning, no hidden instructions.</li>
          <li><b>A Showrunner</b> plans the arc; <b>a Researcher</b> reads Wikipedia, Wookieepedia and the 40K wiki and cuts them into numbered evidence.</li>
          <li><b>A Storyteller</b> narrates only from that evidence; code flags any sentence that cites evidence that doesn't exist.</li>
          <li><b>A Skeptic</b> grades every claim and can send the chapter back for a rewrite.</li>
        </ol>
        <p className="muted">Eleven AI agents in all, each with one job and a hard spending cap. You can watch them work, see what each story cost, and run the safety tests yourself. <button className="linkish" onClick={onSafety}>Settings → Safety &amp; transparency</button></p>
      </section>

      <section className="about-who card">
        <p className="eyebrow">Who made it</p>
        <p>Loremaster was built by <b>Gaurang Singh</b>, Yale SOM MBA 2028, as the final project for MGT 409, AI Foundations for Managers, with an AI coding assistant.
          It was shaped by an AI expert review panel and then by SOM classmates, whose first round of feedback added the card pictures, the Settings page and the new Library.</p>
        <p className="muted small">Stories are AI-written and AI-checked against wiki sources, not primary archives, so treat the grades as a guide rather than the final word. Evidence comes from Wikipedia, Wookieepedia
          and the Warhammer 40k Wiki (CC BY-SA), linked on every claim; card pictures are public-domain or CC images from Wikimedia Commons. An unofficial fan and educational project, not affiliated with Lucasfilm, Disney or Games Workshop.</p>
      </section>
    </div>
  )
}
