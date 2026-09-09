"""
The agent that decides where to look and what to spend.

Built on the LangGraph structure from the notebook, with two changes.

First, the tools do real work now instead of returning fixed strings.

Second, there is a deterministic policy that runs when no model key is
configured, and it is not a stub. A crowd-safety system must not stop working
because an API key expired or a provider had an outage mid-incident, so the
rules are the floor and the model is an improvement on top.

What the model is allowed to decide:
    which zone deserves attention, in what order, how much budget to spend,
    when to stop, and how to explain the decision.

What it may never decide:
    whether people are in danger. That is detect.danger.assess(), a rule that
    can be checked by hand afterwards. If a model made that call, nobody could
    answer "why did it fire" or, far worse, "why did it not".
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from app.ai import tools as T
from app.core.city import city

logger = logging.getLogger("crovia.ai")

SYSTEM_PROMPT = """You manage the API budget for a crowd-safety system in Lusail.

You decide WHERE TO LOOK and WHAT TO SPEND. You never decide whether people are
in danger — call the `judge` tool for that, and report what it says.

Rules you must follow:

1. NETWORK FAULT: if every district reads High at once, that is a network
   problem and not a crowd. Say so and spend nothing.

2. COMPARE AGAINST THE CALM PART OF THE CITY, not the average. When two or
   three districts are genuinely busy, the average is dragged up by the crowds
   themselves and nothing looks unusual.

3. ESCALATE IN ORDER, cheapest first:
       arm_chokepoints  ->  verify_and_filter  ->  retrieve_locations_batch
   Do not skip to the expensive step. Location Retrieval costs about three
   times a verification call.

4. A NARROW LINK MATTERS MORE THAN A BIG CROWD. A zone whose narrowest link is
   9 m can pass about 650 people a minute. If more are arriving than that, the
   queue can only grow. Capacity comes from the city plan and costs nothing.

5. WHEN SEVERAL CROWDS COMPETE, fund the most urgent one properly rather than
   splitting the budget evenly. Three half-funded answers are three samples too
   small to act on.

Always give one short sentence of reasoning before calling a tool."""


@dataclass
class Decision:
    zone_id: str
    action: str
    reasoning: str
    spent: int = 0
    result: dict = field(default_factory=dict)
    by: str = "rules"


class DeterministicPolicy:
    """
    The floor. Same escalation ladder, decided by arithmetic.

    This is what runs with no model configured, and what runs if the model
    fails. It is deliberately the same ladder the prompt describes, so the two
    behave alike and the model is an improvement rather than a different system.
    """

    name = "rules"

    def decide(self, engine, snapshot: dict) -> list[Decision]:
        out: list[Decision] = []
        shares = engine._congestion_signal()
        if shares and all(v > 0.35 for v in shares.values()) and len(shares) > 1:
            return [Decision("-", "suppress",
                             "Every district is elevated together, so this is a network "
                             "fault rather than a crowd. Spending nothing.")]

        baseline = min(shares.values()) if shares else 0.0
        for zone_id, z in city.zones.items():
            zs = engine.zones[zone_id]
            share = shares.get(z.district_id, 0.0)
            rate = zs.rate_per_min()
            capacity = city.zone_capacity_per_min(zone_id)

            if not (share >= 0.10 and share >= 2 * max(baseline, 0.02)) and rate <= 0:
                continue

            if len(zs.counts) < 2:
                out.append(Decision(
                    zone_id, "verify_and_filter",
                    f"{z.label} looks unusual against the calmest district, and there is "
                    f"no count yet, so counting is the cheapest way to find out."))
            elif rate >= 0.45 * capacity:
                out.append(Decision(
                    zone_id, "retrieve_locations_batch",
                    f"{z.label} is filling at about {rate:,.0f} people a minute against a "
                    f"link that passes {capacity:,.0f}. Worth paying to locate."))
            else:
                out.append(Decision(
                    zone_id, "verify_and_filter",
                    f"{z.label} is being watched; another count keeps the rate current."))
        return out


class ModelPolicy:
    """
    The LangGraph agent. Used when a key is configured.

    Falls back to the rules on any failure. An incident is exactly when a
    provider outage would hurt most, so a failure here must degrade rather than
    stop.
    """

    name = "model"

    def __init__(self, model_name: str | None = None) -> None:
        from langchain_groq import ChatGroq
        # The notebook passed a Groq model name to Google's client, which cannot
        # work: llama3-70b-8192 is served by Groq, not by Gemini.
        # The default is what the project's Groq account actually serves. Groq
        # retires model names often, so CROVIA_MODEL overrides it without a code
        # change, and an unknown name falls back to the rules rather than
        # stopping detection.
        self.model = ChatGroq(
            model=model_name or os.getenv("CROVIA_MODEL", "openai/gpt-oss-120b"),
            temperature=0,
        )
        self.fallback = DeterministicPolicy()

    def decide(self, engine, snapshot: dict) -> list[Decision]:
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            situation = _describe(engine, snapshot)
            reply = self.model.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=situation + "\n\nWhich single zone should be looked at "
                                                 "next, which tool should be called, and why? "
                                                 "Answer as: ZONE | TOOL | one sentence."),
            ])
            text = (reply.content or "").strip()
            parts = [p.strip() for p in text.split("|")]
            if len(parts) >= 3 and parts[0] in city.zones:
                return [Decision(parts[0], parts[1], parts[2], by="model")]
            logger.info("model gave no usable decision (%r); using rules", text[:120])
        except Exception as exc:
            logger.warning("model unavailable (%s); using rules", exc)
        return self.fallback.decide(engine, snapshot)


def _describe(engine, snapshot: dict) -> str:
    """The situation, in the plain terms the prompt expects."""
    shares = engine._congestion_signal()
    lines = ["Districts and the share of monitored devices reporting congestion:"]
    for d, v in shares.items():
        lines.append(f"  {city.districts[d].short}: {v:.0%} ({snapshot['districts'].get(d)})")
    lines.append("\nZones:")
    for zid, z in city.zones.items():
        zs = engine.zones[zid]
        people = round(zs.counts[-1][1]) if zs.counts else 0
        lines.append(
            f"  {zid}: narrowest link {city.bottleneck_of(zid).width_m:.0f} m "
            f"(passes {city.zone_capacity_per_min(zid):,.0f}/min), "
            f"about {people:,} people, filling {zs.rate_per_min():+,.0f}/min")
    lines.append(f"\nBudget left this hour: {engine.budget.available(engine.now)} calls.")
    return "\n".join(lines)


def build_policy() -> Any:
    """Model if a key is set, rules otherwise."""
    if os.getenv("GROQ_API_KEY", "").strip():
        try:
            p = ModelPolicy()
            logger.info("AI policy: LangGraph agent on Groq")
            return p
        except Exception as exc:
            logger.warning("could not start the model policy (%s); using rules", exc)
    logger.info("AI policy: deterministic rules (no GROQ_API_KEY set)")
    return DeterministicPolicy()


def run_once(engine) -> list[dict]:
    """
    One decision cycle: choose, act, then let the RULES judge.

    The order matters. The agent gathers evidence and the rule decides danger,
    never the other way round.
    """
    policy = getattr(engine, "_policy", None)
    if policy is None:
        policy = engine._policy = build_policy()

    snapshot = engine.snapshot()
    results: list[dict] = []
    for d in policy.decide(engine, snapshot)[:3]:
        if d.action == "suppress":
            engine.log("agent", d.reasoning, by=policy.name, action="suppress")
            results.append({"zone": d.zone_id, "action": d.action,
                            "reasoning": d.reasoning, "by": policy.name})
            continue

        fn = {"arm_chokepoints": T.arm_chokepoints,
              "verify_and_filter": T.verify_and_filter,
              "retrieve_locations_batch": T.retrieve_locations_batch}.get(d.action)
        if fn is None:
            continue

        before = engine.ledger.total
        d.result = fn(engine, d.zone_id)
        d.spent = engine.ledger.total - before
        verdict = T.judge(engine, d.zone_id)

        engine.log("agent", f"{d.reasoning} [{d.action}, {d.spent} calls]",
                   by=policy.name, action=d.action, zone=d.zone_id)
        results.append({"zone": d.zone_id, "action": d.action, "reasoning": d.reasoning,
                        "by": policy.name, "calls_spent": d.spent,
                        "result": d.result, "verdict": verdict})
    return results
