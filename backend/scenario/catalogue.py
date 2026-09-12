"""
The scenarios a visitor can choose from, and what each one is really testing.

Six evenings in Lusail. Two should raise an alarm, three must not, and one
should raise a LATE alarm and is included precisely because it shows a weakness
rather than a strength.

WHY THE SAFE ONES OUTNUMBER THE DANGEROUS ONES
----------------------------------------------
A city has perhaps one dangerous evening in twenty. A test suite where half the
evenings are disasters describes a world nobody lives in, and the false-alarm
rate measured on it means nothing - yet that rate is the number which decides
whether an operator ever trusts the system again. So the ordinary evenings
carry more weight here than the catastrophic one.

WHAT EVERY SCENARIO SHARES
--------------------------
App ownership varies almost five-fold between districts, so the counting panel
genuinely misrepresents the city. The population figure CROVIA multiplies by is
deliberately a little wrong. Nothing in the simulated world uses `width * 72` -
the detector's own formula - so when its arithmetic predicts what happens, that
is a result and not a restatement.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Phase:
    """One stretch of an evening."""

    name: str
    minutes: float
    note: str


@dataclass
class Spec:
    """
    Everything that makes one scenario different from another.

    Written as data rather than code so a scenario can be added, or an existing
    one argued with, without touching the world or the network.
    """

    key: str
    title: str
    # Plain language, for somebody who has never seen the code.
    what_happens: str
    why_it_is_hard: str
    # The honest expectation. A scenario that cannot fail proves nothing.
    should_fire: bool
    expected: str

    schedule: list[Phase]
    attendees: int = 18_000
    egress_zone: str = "zone_stadium_north_concourse"

    # How many of the planned 30,000 are really present. Anything below 1.0
    # means CROVIA scales its headcount by a denominator that is wrong.
    present_share: float = 0.92

    # App ownership per district, as multipliers. Unequal on purpose: this is
    # what stops the counting panel being a perfect sample of the city.
    app_share_by_district: dict[str, float] = field(default_factory=lambda: {
        "district_central": 1.8,
        "district_stadium": 1.1,
        "district_marina": 0.9,
        "district_foxhills": 0.4,
    })

    # Truth against the plan. Below 1.0 means the link is NARROWER in reality
    # than the map believes - a barrier, a parked van, a closed gate.
    width_error: dict[str, float] = field(default_factory=dict)

    # How often the network cannot answer at all.
    unknown_prob: float = 0.23

    # Congestion that has nothing to do with crowds - somebody streaming video.
    # Raises every district's reading without any extra people.
    congestion_noise: float = 0.0

    # Multiplies how quickly people leave the venue. Below 1.0 is a staggered,
    # well-managed release; above 1.0 is everyone at once.
    release_rate: float = 1.0

    # Share of app users who are enrolled and watched.
    coverage: float = 1.0


CALM = Phase("calm", 10, "An ordinary evening. People are near home, moving slowly.")


CATALOGUE: list[Spec] = [

    # ---------------------------------------------------------------- 1
    Spec(
        key="egress",
        title="Full time at the stadium",
        what_happens=(
            "Eighteen thousand people watch a match, then all leave at once "
            "through a concourse that narrows to nine metres. More people "
            "arrive at the ramp each minute than it can possibly pass, so they "
            "pile up against it."
        ),
        why_it_is_hard=(
            "The danger has to be spotted while the ramp still looks half "
            "empty. By the time it is visibly full, nobody inside can move and "
            "there is nothing useful left to do."
        ),
        should_fire=True,
        expected=(
            "No alarm during the match. An alarm during egress, several "
            "minutes before the ramp becomes dangerous, followed by an "
            "all-clear once the crowd disperses."
        ),
        schedule=[
            CALM,
            Phase("arrival", 25, "The crowd travels in and goes inside the bowl."),
            Phase("match", 20, "Everyone seated. Packed, and completely safe."),
            Phase("egress", 26, "Full time. The crowd funnels into the 9 m ramp."),
            Phase("dispersal", 20, "People clear the zone and walk away."),
        ],
    ),

    # ---------------------------------------------------------------- 2
    Spec(
        key="not_clearing",
        title="The exit is blocked",
        what_happens=(
            "The same crowd leaves, but the route beyond the ramp is "
            "obstructed, so people enter the zone and do not come out. The "
            "number inside climbs and stops falling."
        ),
        why_it_is_hard=(
            "Arrivals are not unusually fast, so the earliest alarm - more "
            "coming in than can get out - may never fire. The system has to "
            "notice that people who went in are not coming out, which is a "
            "different question entirely."
        ),
        should_fire=True,
        expected="An alarm raised by the 'not clearing' rule rather than by the fill rate.",
        schedule=[
            CALM,
            Phase("arrival", 25, "The crowd travels in and goes inside."),
            Phase("match", 15, "Everyone seated."),
            Phase("egress", 26, "They leave, but the way out beyond the ramp is blocked."),
            Phase("dispersal", 18, "The obstruction clears and the zone empties."),
        ],
        width_error={"seg_north_plaza": 0.15},   # the route beyond the ramp is choked
    ),

    # ---------------------------------------------------------------- 3
    Spec(
        key="seated_crowd",
        title="A packed stadium that is perfectly safe",
        what_happens=(
            "Eighteen thousand people sit through a match. Every cell tower "
            "around the stadium is saturated and congestion reads High across "
            "the whole district for the better part of an hour."
        ),
        why_it_is_hard=(
            "This is the test a naive detector fails. Everything that looks "
            "like danger is present - enormous density, saturated network, a "
            "huge crowd in one place - and none of it is dangerous, because "
            "nobody is moving and nobody is trapped. A system that treats "
            "'crowded' as 'dangerous' fires here and is wrong."
        ),
        should_fire=False,
        expected=(
            "Money is spent looking, which is correct. No alarm at any point, "
            "and no warning sent to anybody."
        ),
        schedule=[
            CALM,
            Phase("arrival", 25, "The crowd travels in and goes inside the bowl."),
            Phase("match", 45, "Everyone seated, packed, still. Towers saturated."),
            Phase("dispersal", 10, "The match is still on. Nothing has happened."),
        ],
    ),

    # ---------------------------------------------------------------- 4
    Spec(
        key="near_miss",
        title="A crowd that almost becomes dangerous",
        what_happens=(
            "A smaller crowd leaves over a longer period. The ramp fills to "
            "roughly three and a half people per square metre - uncomfortable, "
            "close to the line - and then drains without ever crossing it."
        ),
        why_it_is_hard=(
            "This is where false alarms live. The measurement is noisy enough "
            "that a single high sample can look like the real thing, and a "
            "detector tuned slightly too tight will fire on an evening where "
            "nothing whatsoever went wrong."
        ),
        should_fire=False,
        expected=(
            "The zone is watched closely and may reach the confirming state. "
            "No alarm. If this one fires, the thresholds are too tight."
        ),
        schedule=[
            CALM,
            Phase("arrival", 20, "A smaller crowd arrives."),
            Phase("match", 15, "Seated."),
            Phase("egress", 22, "They leave gradually. It gets tight, and holds."),
            Phase("dispersal", 15, "The zone empties."),
        ],
        attendees=7_500,
        release_rate=0.45,
    ),

    # ---------------------------------------------------------------- 5
    Spec(
        key="network_fault",
        title="A network fault that looks like a crowd everywhere",
        what_happens=(
            "No unusual crowd anywhere in Lusail. A fault in the operator's "
            "network makes congestion read High across all four districts at "
            "once, including places where nobody has gathered."
        ),
        why_it_is_hard=(
            "Congestion is the signal that decides where to spend money. If "
            "the system believes it blindly it will now spend its entire "
            "hourly budget investigating four districts where nothing is "
            "happening - and have nothing left when something real begins."
        ),
        should_fire=False,
        expected=(
            "The system recognises that everywhere being elevated at once is a "
            "fault rather than a crowd, says so, and spends almost nothing."
        ),
        schedule=[
            CALM,
            Phase("arrival", 10, "Still an ordinary evening."),
            Phase("match", 25, "The fault persists. Every district reads High."),
            Phase("dispersal", 10, "The fault clears."),
        ],
        attendees=0,
        congestion_noise=0.85,
    ),

    # ---------------------------------------------------------------- 6
    Spec(
        key="wrong_map",
        title="The map is wrong about the ramp",
        what_happens=(
            "The same full-time egress, except the nine metre ramp is only six "
            "and a half metres wide in reality - a barrier has been left in "
            "place. CROVIA reads the plan and believes the ramp can pass 648 "
            "people a minute when the truth is about 470."
        ),
        why_it_is_hard=(
            "Every number CROVIA produces starts from a width it takes on "
            "trust from the city plan. When the plan is wrong, the system is "
            "confidently wrong in the most dangerous direction: it thinks "
            "there is more room than there is, so it warns late."
        ),
        should_fire=True,
        expected=(
            "An alarm, but noticeably later than the same crowd with a correct "
            "map. This scenario is included to measure a weakness, not to "
            "demonstrate a strength - compare its warning time against "
            "'egress' to see the cost of a bad survey."
        ),
        schedule=[
            CALM,
            Phase("arrival", 25, "The crowd travels in and goes inside."),
            Phase("match", 20, "Everyone seated."),
            Phase("egress", 26, "Full time - through a ramp narrower than the plan says."),
            Phase("dispersal", 20, "The zone clears."),
        ],
        width_error={"seg_concourse_ramp": 0.72},
    ),
]


BY_KEY = {s.key: s for s in CATALOGUE}


def listing() -> list[dict]:
    """The catalogue as a visitor should see it, without any code."""
    return [
        {
            "key": s.key,
            "title": s.title,
            "what_happens": s.what_happens,
            "why_it_is_hard": s.why_it_is_hard,
            "should_an_alarm_fire": s.should_fire,
            "what_to_expect": s.expected,
            "runs_for_minutes": round(sum(p.minutes for p in s.schedule)),
            "phases": [p.name for p in s.schedule],
            "attendees": s.attendees,
        }
        for s in CATALOGUE
    ]
