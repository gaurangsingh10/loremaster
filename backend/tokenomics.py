"""Token accounting: price every model run from the API's real usage and bill it to the agent that made it.

OpenAI's input_tokens already include cached reads and cache writes, so those are billed at their own
rates and only the remainder at the full input rate (Lecture 11 / HW6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import EPISODE_BUDGET_USD, MODEL_NAME, PRICES
from models import AgentUsage


class BudgetExceeded(Exception):
    """Raised before the next model call once an episode has spent its budget."""


def price(input_tokens: int, cached: int, cache_write: int, output_tokens: int, model: str = MODEL_NAME) -> float:
    p = PRICES[model]
    cached = min(cached, input_tokens)
    cache_write = min(cache_write, input_tokens - cached)
    uncached = input_tokens - cached - cache_write
    return (uncached * p["input"] + cached * p["cached_input"] + cache_write * p["cache_write"]
            + output_tokens * p["output"]) / 1_000_000


@dataclass
class Ledger:
    budget_usd: float = EPISODE_BUDGET_USD
    accounts: dict[str, AgentUsage] = field(default_factory=dict)
    extra_usd: float = 0.0  # non-token costs (optional TTS), tracked separately

    @property
    def total_usd(self) -> float:
        return sum(a.cost_usd for a in self.accounts.values()) + self.extra_usd

    def check(self) -> None:
        if self.total_usd >= self.budget_usd:
            raise BudgetExceeded(f"episode budget ${self.budget_usd:.4f} reached (spent ${self.total_usd:.5f})")

    def charge(self, agent: str, usage) -> dict:
        """Bill one pydantic-ai RunUsage to `agent`. Returns the per-run numbers (for audit + SSE)."""
        inp = usage.input_tokens or 0
        cached = getattr(usage, "cache_read_tokens", 0) or 0
        write = getattr(usage, "cache_write_tokens", 0) or 0
        out = usage.output_tokens or 0
        cost = price(inp, cached, write, out)
        a = self.accounts.setdefault(agent, AgentUsage(agent=agent))
        a.requests += usage.requests or 0
        a.input_tokens += inp
        a.cached_tokens += cached
        a.cache_write_tokens += write
        a.output_tokens += out
        a.cost_usd = round(a.cost_usd + cost, 8)
        return {"agent": agent, "requests": usage.requests, "input_tokens": inp, "cached_tokens": cached,
                "cache_write_tokens": write, "output_tokens": out, "cost_usd": round(cost, 8)}

    def snapshot(self) -> dict:
        return {"model": MODEL_NAME, "budget_usd": self.budget_usd, "total_usd": round(self.total_usd, 8),
                "agents": [a.model_dump() for a in self.accounts.values()], "extra_usd": round(self.extra_usd, 6)}

    def usage_list(self) -> list[AgentUsage]:
        return list(self.accounts.values())
