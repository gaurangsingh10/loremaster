export type Grade = 'Documented' | 'Debated' | 'Legend' | 'Canon' | 'Legends' | 'Conflicting' | 'Fan theory' | 'Unsupported'
export type Mode = 'crossover' | 'history' | 'lore'

export interface Thread { id: string; title: string; hook: string; mode: Mode; packs: string[]; era: string; universe: string; curated: boolean; genre?: string }
export interface EvidenceCard { id: string; pack: string; page_title: string; url: string; snippet: string; license: string }
export interface GradedClaim { id: string; text: string; kind: 'history' | 'lore'; grade: Grade; note: string; evidence: EvidenceCard[] }
export interface MythItem { statement: string; verdict: 'fact' | 'myth' | 'debated'; explanation: string; evidence_ids: string[]; evidence: EvidenceCard[] }
export interface CallIt { question: string; options: string[]; answer_index: number; reveal_para: number; explanation: string }
export interface ChapterGames { myth_or_fact: MythItem[]; call_it: CallIt | null }
export interface Chapter { index: number; title: string; narration: string; claims: GradedClaim[]; branch_options: string[]; revised: boolean; chosen_branch: string | null; games?: ChapterGames | null }
export interface Answer { id: string; question: string; answer: string; on_topic: boolean; claims: { text: string; grade: Grade; evidence_ids: string[]; evidence: EvidenceCard[] }[]; refused?: boolean; reason?: string }
export interface AgentUsage { agent: string; requests: number; input_tokens: number; cached_tokens: number; cache_write_tokens: number; output_tokens: number; cost_usd: number }
export interface ReadingItem { title: string; author: string; year: number | null; why: string; url: string }
export interface Episode {
  id: string; thread: Thread; minutes: number; total_chapters: number; title: string; logline: string
  chapters: Chapter[]; reading: ReadingItem[]; usage: AgentUsage[]; total_usd: number
  status: 'running' | 'waiting_choice' | 'done' | 'budget_stop' | 'refused' | 'error'; stop_reason: string; demo: boolean
}
export interface Health { ok: boolean; model: string; data_mode: string; has_key: boolean; demo_only: boolean; tts: boolean; budget_usd: number }
export interface Spend { model: string; budget_usd: number; total_usd: number; agents: AgentUsage[] }
export interface AgentActivity { agent: string; state: 'idle' | 'working' | 'done' | 'error'; label: string; lastTool?: string; seconds?: number; cost?: number }
