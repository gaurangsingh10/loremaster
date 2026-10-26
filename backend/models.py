"""Every structured type in the app: the contracts between agents, the API and the UI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PackId = Literal["history", "star_wars", "warhammer40k", "science", "technology", "politics"]
Mode = Literal["crossover", "history", "lore"]

# Grades. History and fiction use different scales; "Unsupported" is shared and means "no evidence".
HISTORY_GRADES = ("Documented", "Debated", "Legend", "Interpretation", "Unsupported")
LORE_GRADES = ("Canon", "Legends", "Conflicting", "Fan theory", "Interpretation", "Unsupported")
Grade = Literal["Documented", "Debated", "Legend", "Canon", "Legends", "Conflicting", "Fan theory", "Interpretation", "Unsupported"]


# ---------------------------------------------------------------- Guardian
class GuardVerdict(BaseModel):
    """Gate before any money is spent. Kept tiny on purpose (a cheap 'choice' call)."""
    allowed: bool
    category: Literal["ok", "off_topic", "harmful_history", "hate_or_harassment", "prompt_injection", "too_long",
                      "partisan_politics", "medical_or_legal_advice"]
    reason: str = Field(description="One short sentence the listener will see.")
    safe_reframe: str | None = Field(default=None, description="A respectful alternative topic, if refused.")


# ---------------------------------------------------------------- Menu / Showrunner
class Thread(BaseModel):
    id: str
    title: str
    hook: str = Field(description="One line that makes a commuter want to press play.")
    mode: Mode
    packs: list[PackId]
    era: str = ""
    universe: str = ""
    curated: bool = False
    genre: str = ""   # history | science | technology | politics | lore (UI grouping + quiz matching)


class ChapterBeat(BaseModel):
    title: str
    focus: str = Field(description="What this chapter must cover, in one or two sentences.")
    queries: list[str] = Field(description="2-4 wiki search queries for the Researcher, tagged by pack.", default_factory=list)
    packs: list[PackId] = Field(default_factory=list)


class EpisodePlan(BaseModel):
    title: str
    logline: str
    chapters: list[ChapterBeat]


class NextBeat(BaseModel):
    """Showrunner's plan for the chapter after the listener picks a branch."""
    title: str
    focus: str
    queries: list[str]
    packs: list[PackId]


# ---------------------------------------------------------------- Researcher
class EvidenceCard(BaseModel):
    id: str                      # e.g. "E3", assigned by code, never by the model
    pack: PackId
    page_title: str
    url: str
    snippet: str                 # sanitized, <= CARD_CHARS
    license: str = "CC BY-SA"


class ResearchPick(BaseModel):
    """What the Researcher agent returns: which cards (by id) are worth narrating, and why."""
    keep_card_ids: list[str]
    gaps: list[str] = Field(default_factory=list, description="What it looked for but could not find.")


# ---------------------------------------------------------------- Storyteller
class Claim(BaseModel):
    id: str = Field(description="c1, c2 ... in order of appearance")
    text: str = Field(description="The factual claim, restated plainly in one sentence.")
    evidence_ids: list[str] = Field(default_factory=list, description="Evidence card ids that support it, e.g. ['E2'].")
    kind: Literal["history", "lore"]


class ChapterDraft(BaseModel):
    title: str
    narration: str = Field(description="Spoken narration. Each factual sentence ends with a tag like [c1].")
    claims: list[Claim]
    branch_options: list[str] = Field(description="Exactly 3 distinct next-chapter directions, each under 12 words.")


# ---------------------------------------------------------------- Skeptic
class ClaimGrade(BaseModel):
    claim_id: str
    grade: Grade
    note: str = Field(description="One sentence: why this grade, citing what the evidence does or doesn't say.")
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimGrades(BaseModel):
    grades: list[ClaimGrade]
    rewrite_needed: bool = Field(description="True if any claim is Unsupported and should be fixed or flagged.")
    rewrite_instructions: str = ""


# ---------------------------------------------------------------- Librarian
class ReadingItem(BaseModel):
    title: str
    author: str
    year: int | None = None
    why: str = Field(description="One sentence in our own words. Never quote the book.")
    url: str = ""


class ReadingList(BaseModel):
    items: list[ReadingItem]


# ---------------------------------------------------------------- What the UI renders
class GradedClaim(BaseModel):
    id: str
    text: str
    kind: Literal["history", "lore"]
    grade: Grade
    note: str
    evidence: list[EvidenceCard]


# ---------------------------------------------------------------- Interactive: games + ask
class MythDraft(BaseModel):
    statement: str = Field(description="One plain, assertive sentence a listener judges, e.g. 'Nero played the fiddle while Rome burned.'")
    verdict: Literal["fact", "myth", "debated"]
    explanation: str = Field(description="One or two sentences: what the evidence actually says.")
    evidence_ids: list[str] = Field(default_factory=list)


class CallItDraft(BaseModel):
    question: str = Field(description="'What do you think happened next?'-style question answered later in the chapter.")
    options: list[str] = Field(description="Exactly 3 short, plausible options.")
    answer_index: int = Field(ge=0, le=2)
    reveal_para: int = Field(description="0-based index of the paragraph that reveals the answer (must be >= 1).")
    explanation: str


class GamesDraft(BaseModel):
    myth_or_fact: list[MythDraft]
    call_it: CallItDraft | None = None


class MythItem(MythDraft):
    evidence: list[EvidenceCard] = Field(default_factory=list)


class ChapterGames(BaseModel):
    myth_or_fact: list[MythItem] = Field(default_factory=list)
    call_it: CallItDraft | None = None


class AnswerClaim(BaseModel):
    text: str
    grade: Grade
    evidence_ids: list[str] = Field(default_factory=list)


class AnswerDraft(BaseModel):
    answer: str = Field(description="Spoken answer, 40-130 words, in the narrator's voice.")
    claims: list[AnswerClaim] = Field(default_factory=list)
    on_topic: bool = True


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    chapter: int = 1


class Chapter(BaseModel):
    index: int
    title: str
    narration: str
    claims: list[GradedClaim]
    branch_options: list[str]
    revised: bool = False
    chosen_branch: str | None = None
    games: ChapterGames | None = None


class AgentUsage(BaseModel):
    agent: str
    requests: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Episode(BaseModel):
    id: str
    thread: Thread
    minutes: int
    total_chapters: int
    title: str = ""
    logline: str = ""
    chapters: list[Chapter] = Field(default_factory=list)
    plan: list[ChapterBeat] = Field(default_factory=list)
    reading: list[ReadingItem] = Field(default_factory=list)
    usage: list[AgentUsage] = Field(default_factory=list)
    total_usd: float = 0.0
    status: Literal["running", "waiting_choice", "done", "budget_stop", "refused", "error", "stopped"] = "running"
    stop_reason: str = ""
    demo: bool = False


# ---------------------------------------------------------------- API requests
class EpisodeRequest(BaseModel):
    instant_id: str | None = Field(default=None, description="Play a pre-built Instant Story (no wait).")
    thread_id: str | None = None
    topic: str | None = Field(default=None, description="Free-text 'Ask about anything'.")
    mode: Mode = "crossover"
    minutes: Literal[10, 20, 40] = 10
    budget_usd: float | None = None      # only lowered (safety demo); never raised above the hard cap
    defenses: str = "all"                 # all | none | code | design | prompt (Safety Lab)
    skeptic: Literal["full", "lite", "off"] = "full"


class ChoiceRequest(BaseModel):
    branch: str


class Feedback(BaseModel):
    episode_id: str | None = None
    rating: int = Field(ge=1, le=5)
    minutes_listened: int | None = None
    listen_tomorrow: bool | None = None
    favorite_moment: str = ""
    quote: str = ""
    name: str = ""
    role: str = ""


# ---------------------------------------------------------------- Audit
class AuditEntry(BaseModel):
    ts: str
    episode_id: str
    agent: str
    event: str                       # agent_started | tool_call | agent_done | quarantine | budget_stop | refused | error
    tool: str | None = None
    args: str | None = None
    result: str | None = None
    tokens: dict | None = None
    stop_reason: str | None = None


# ---------------------------------------------------------------- Snap & Story, Interview, Concierge
class SnapID(BaseModel):
    what: str
    kind: Literal["artifact", "building", "artwork", "book", "miniature", "place", "document", "other"]
    confidence: Literal["high", "medium", "low"]
    visible_clues: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    story_topic: str
    mode: Mode = "history"
    hook: str = ""
    safe: bool = True
    reason: str = ""


class InterviewAnswer(BaseModel):
    in_character: str
    claims: list[AnswerClaim] = Field(default_factory=list)
    aside: str = ""


class InterviewStart(BaseModel):
    character: str = Field(min_length=2, max_length=80)


class InterviewAsk(BaseModel):
    question: str = Field(min_length=2, max_length=300)


class ConciergePick(BaseModel):
    instant_id: str
    why: str


class ConciergeReply(BaseModel):
    message: str
    picks: list[ConciergePick] = Field(default_factory=list)
    live_idea: str = ""


class ConciergeAsk(BaseModel):
    message: str = Field(min_length=2, max_length=300)
