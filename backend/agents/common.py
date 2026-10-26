"""Shared agent plumbing: prompt assembly (cache-friendly), the per-episode context, and one guarded runner.

Every model call in the app goes through `run_agent`, which:
  1. checks the episode budget BEFORE spending (BudgetExceeded stops the episode cleanly),
  2. runs the agent under hard UsageLimits (requests, tool calls, tokens) so it can't loop,
  3. bills the real API usage to that agent in the Ledger,
  4. appends to the audit trail and emits live events for the UI.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.usage import RunUsage
from pydantic_ai.exceptions import ModelHTTPError

import asyncio

RETRY_DELAYS = (1.5, 4.0)   # seconds; transient gateway/provider errors get two more tries


def _transient(e: BaseException) -> bool:
    """500/502/503/504 from the gateway or provider, 429 rate limits, and network timeouts are worth retrying."""
    if isinstance(e, ModelHTTPError):
        return e.status_code in (429, 500, 502, 503, 504)
    name = type(e).__name__
    return name in ("APITimeoutError", "APIConnectionError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError")

from audit import audit, short
from config import (MAX_OUTPUT_TOKENS, PROMPTS_DIR, REQUEST_LIMIT_PER_AGENT_RUN, TOOL_CALLS_LIMIT_PER_AGENT_RUN,
                    TOTAL_TOKENS_LIMIT_PER_AGENT_RUN, build_model)
from tokenomics import Ledger
from tools import CardRegistry

ALL_LAYERS = frozenset({"code", "design", "prompt"})

Emit = Callable[[dict], Awaitable[None]]


async def _noop(_: dict) -> None:
    return None


def parse_layers(spec: str | None) -> frozenset[str]:
    if not spec or spec == "all":
        return ALL_LAYERS
    if spec == "none":
        return frozenset()
    layers = frozenset(x.strip() for x in spec.split(",") if x.strip())
    return layers & ALL_LAYERS


@dataclass
class EpisodeContext:
    episode_id: str
    ledger: Ledger
    emit: Emit = _noop
    layers: frozenset[str] = ALL_LAYERS
    cache: bool = True
    skeptic: str = "full"                     # full | lite | off
    registry: CardRegistry = field(default_factory=CardRegistry)
    injected_pages: list[dict] = field(default_factory=list)   # Safety Lab fixtures
    quarantined: list[str] = field(default_factory=list)
    cancelled: bool = False

    async def event(self, type_: str, **data: Any) -> None:
        await self.emit({"type": type_, "ts": time.time(), **data})


# ------------------------------------------------------------------ prompts
def load_instructions(role: str, layers: frozenset[str], with_style: bool = False) -> str:
    """Static, long prefix first (house rules [+ style guide]) then the role prompt, so it caches well."""
    house = (PROMPTS_DIR / "house_rules.md").read_text()
    if "prompt" not in layers:  # Safety Lab: turn the prompt-level defense off
        house = re.sub(r"<!-- @security -->.*?<!-- @end -->", "", house, flags=re.S)
    else:
        house = house.replace("<!-- @security -->", "").replace("<!-- @end -->", "")
    parts = [house.strip()]
    if with_style:
        parts.append((PROMPTS_DIR / "style_guide.md").read_text().strip())
    parts.append((PROMPTS_DIR / f"{role}.md").read_text().strip())
    return "\n\n---\n\n".join(parts)


_AGENTS: dict[tuple, Agent] = {}


def get_agent(role: str, output_type, *, layers: frozenset[str], cache: bool = True, tools: list | None = None,
              deps_type=type(None), with_style: bool = False, effort: str = "low") -> Agent:
    key = (role, output_type, layers, cache, with_style, effort, bool(tools))
    if key in _AGENTS:
        return _AGENTS[key]
    static = load_instructions(role, layers, with_style)
    if cache:
        instructions: Any = static
        settings = {"openai_prompt_cache_key": f"loremaster-{role}-{'-'.join(sorted(layers)) or 'none'}"}
    else:
        def instructions() -> str:  # re-evaluated every request: a random first line defeats prefix caching
            return f"[cache-buster {uuid.uuid4().hex}]\n\n" + static
        settings = {}
    settings.update({"max_tokens": MAX_OUTPUT_TOKENS, "openai_reasoning_effort": effort})
    agent = Agent(build_model(), output_type=output_type, instructions=instructions, tools=tools or [],
                  deps_type=deps_type, model_settings=settings, retries=2)
    _AGENTS[key] = agent
    return agent


LIMITS = UsageLimits(request_limit=REQUEST_LIMIT_PER_AGENT_RUN, tool_calls_limit=TOOL_CALLS_LIMIT_PER_AGENT_RUN,
                     total_tokens_limit=TOTAL_TOKENS_LIMIT_PER_AGENT_RUN)


async def run_agent(ectx: EpisodeContext, role: str, agent: Agent, prompt: str, *, deps=None, label: str = ""):
    """The one guarded way to call a model. Returns the agent's typed output."""
    if ectx.cancelled:
        raise RuntimeError("episode cancelled")
    ectx.ledger.check()  # overspend guard BEFORE the call
    await ectx.event("agent_started", agent=role, label=label)
    audit(ectx.episode_id, role, "agent_started", args=label or prompt[:200])
    t0 = time.time()
    usage = RunUsage()  # shared with the run, so tokens are billed even if the run fails midway
    try:
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                result = await agent.run(prompt, deps=deps, usage_limits=LIMITS, usage=usage)
                break
            except Exception as e:
                if attempt >= len(RETRY_DELAYS) or not _transient(e) or ectx.cancelled:
                    raise
                delay = RETRY_DELAYS[attempt]
                audit(ectx.episode_id, role, "retry", result=f"{type(e).__name__}: {str(e)[:160]}", stop_reason=f"retrying in {delay}s")
                await ectx.event("agent_retry", agent=role, label=label, attempt=attempt + 2, delay=delay,
                                 error=f"{type(e).__name__} {getattr(e, 'status_code', '')}".strip())
                await asyncio.sleep(delay)
                ectx.ledger.check()  # never retry past the budget
    except BaseException as e:
        if usage.requests:
            ectx.ledger.charge(role, usage)
            await ectx.event("spend", **ectx.ledger.snapshot())
        audit(ectx.episode_id, role, "error", result=f"{type(e).__name__}: {e}")
        await ectx.event("agent_error", agent=role, error=f"{type(e).__name__}: {str(e)[:200]}")
        raise
    bill = ectx.ledger.charge(role, usage)
    secs = round(time.time() - t0, 1)
    audit(ectx.episode_id, role, "agent_done", result=short(result.output.model_dump() if hasattr(result.output, "model_dump") else result.output, 400),
          tokens=bill, stop_reason=f"output ready in {secs}s")
    await ectx.event("agent_done", agent=role, label=label, seconds=secs, usage=bill)
    await ectx.event("spend", **ectx.ledger.snapshot())
    return result.output
