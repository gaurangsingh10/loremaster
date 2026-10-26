"""Guardian: code rules first (free), then one cheap model call, before any money is spent on an episode."""

from __future__ import annotations

import re

from agents.common import EpisodeContext, get_agent, run_agent
from config import MAX_TOPIC_CHARS
from models import GuardVerdict

DENIAL = re.compile(
    r"\b(holocaust|shoah|armenian genocide|rwandan genocide|srebrenica|nanking|nanjing|holodomor|slave trade|slavery)\b"
    r".{0,60}\b(hoax|fake|invented|never happened|didn'?t happen|myth|lie|exaggerat\w*|debunk\w*)\b"
    r"|\b(hoax|fake|invented|never happened|myth|lie|debunk\w*)\b.{0,60}\b(holocaust|shoah|genocide)\b",
    re.I)
GLORIFY = re.compile(r"\b(glorious|heroic|based|epic) (lore|story|saga) of (the )?(nazi|ss|kkk|isis|third reich)\b"
                     r"|\b(nazi|ss|kkk)\b.{0,40}\b(heroes|were right|did nothing wrong)\b", re.I)
PARTISAN = re.compile(r"\b(who should i vote for|tell (me|people) (who|how) to vote|why (you should|to) vote (for|against)|"
                      r"(convince|persuade) (me|people) to (vote|support)|campaign (ad|speech) for)\b", re.I)
INJECTION = re.compile(r"ignore (all |your |previous )*(instructions|rules)|system prompt|reveal (your )?(prompt|key)"
                       r"|api[_ ]?key|you are now|developer mode", re.I)


def code_check(topic: str) -> GuardVerdict | None:
    if len(topic) > MAX_TOPIC_CHARS:
        return GuardVerdict(allowed=False, category="too_long", reason=f"Please keep topics under {MAX_TOPIC_CHARS} characters.")
    if INJECTION.search(topic):
        return GuardVerdict(allowed=False, category="prompt_injection",
                            reason="That looks like an attempt to change how Loremaster works, so I can't run it.")
    if PARTISAN.search(topic):
        return GuardVerdict(allowed=False, category="partisan_politics",
                            reason="Loremaster explains how politics works and where ideas came from, but won't campaign or tell you how to vote.",
                            safe_reframe="The history of this issue and the strongest arguments on each side")
    if DENIAL.search(topic) or GLORIFY.search(topic):
        return GuardVerdict(allowed=False, category="harmful_history",
                            reason="Loremaster tells documented history honestly and won't deny or glorify atrocities.",
                            safe_reframe="How historians documented it: the evidence and the trials")
    return None


async def check(ectx: EpisodeContext, topic: str, use_model: bool = True) -> GuardVerdict:
    verdict = code_check(topic)
    if verdict:
        await ectx.event("guard", agent="guardian", verdict=verdict.model_dump(), layer="code")
        return verdict
    if not use_model:
        return GuardVerdict(allowed=True, category="ok", reason="Curated thread.")
    agent = get_agent("guardian", GuardVerdict, layers=ectx.layers, cache=ectx.cache, effort="low")
    verdict = await run_agent(ectx, "guardian", agent, f"<listener_request>{topic}</listener_request>",
                              label="screen request")
    verdict.allowed = verdict.allowed and verdict.category == "ok"
    await ectx.event("guard", agent="guardian", verdict=verdict.model_dump(), layer="model")
    return verdict
