"""
Test scenarios.

Roughly half contain no danger at all, because a crowd detector is only as
good as its silence. The ones that matter most here are the simultaneous
crowds: a single incident can simply spend what it needs, but two at once have
to share a fixed budget, and that is where the design either holds or does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.twin import Event, Population


@dataclass
class Scenario:
    # Events the operator knows about in advance (a fixture list). Spontaneous
    # crowds are left out on purpose, so both paths get tested.
    key: str
    title: str
    description: str
    # zone id -> whether a genuine crush is expected there
    expect: dict[str, bool]
    events: list[Event] = field(default_factory=list)
    pop: Population = field(default_factory=Population)
    duration_s: float = 45 * 60.0
    budget_per_hour: int = 6000
    rate_limit: dict | None = None
    sentinels_per_district: int = 60
    panel_size: int = 400
    scheduled: list[str] = field(default_factory=list)
    notes: str = ""


STADIUM = "zone_stadium_north_concourse"
TRAM = "zone_stadium_tram_link"
MARINA = "zone_marina_promenade"
CENTRAL = "zone_central_plaza_crossing"
FOXHILLS = "zone_foxhills_crossing"


def all_scenarios() -> list[Scenario]:
    return [
        Scenario(
            key="single_crush", scheduled=[STADIUM],
            title="One crush: stadium egress",
            description="12,000 people leave over 12 minutes through a 9 m ramp that can "
                        "pass about 650/min. The baseline case.",
            expect={STADIUM: True},
            events=[Event(STADIUM, 12_000, duration_s=12 * 60, label="match")],
        ),
        Scenario(
            key="single_safe", scheduled=[STADIUM],
            title="Same crowd, gates opened",
            description="Identical 12,000-person egress, but the constrained links are three "
                        "times wider. Density rises, the crowd keeps moving. Silence is correct.",
            expect={STADIUM: False},
            events=[Event(STADIUM, 12_000, duration_s=12 * 60, width_scale=3.0)],
            notes="False-alarm test: high density with good drainage.",
        ),
        Scenario(
            key="two_crowds_both_dangerous", scheduled=[STADIUM, MARINA],
            title="TWO crushes at once: stadium and marina",
            description="A match empties while a waterfront event lets out. Both bottlenecks "
                        "are overwhelmed at the same time and must share one budget. Tests "
                        "whether the more urgent one is funded first without abandoning the other.",
            expect={STADIUM: True, MARINA: True},
            events=[
                Event(STADIUM, 12_000, start_s=0, duration_s=12 * 60, label="match"),
                Event(MARINA, 9_000, start_s=120, duration_s=7 * 60, label="waterfront"),
            ],
            notes="The case that makes budget allocation matter.",
        ),
        Scenario(
            key="two_crowds_one_safe", scheduled=[STADIUM],
            title="Two crowds, only one dangerous",
            description="A real crush at the stadium and a large but well-drained crowd at "
                        "Central. Must alarm on one and stay silent on the other while both "
                        "compete for the same budget.",
            expect={STADIUM: True, CENTRAL: False},
            events=[
                Event(STADIUM, 12_000, start_s=0, duration_s=12 * 60),
                Event(CENTRAL, 9_000, start_s=60, duration_s=25 * 60),
            ],
            notes="Discrimination under competition.",
        ),
        Scenario(
            key="three_crowds", scheduled=[STADIUM, MARINA, FOXHILLS],
            title="THREE crowds at once",
            description="Stadium, marina and Fox Hills all release together. More demand than "
                        "budget. Zones that cannot be funded must be reported as unresolved, "
                        "never as safe.",
            expect={STADIUM: True, MARINA: True, FOXHILLS: True},
            events=[
                Event(STADIUM, 11_000, start_s=0, duration_s=11 * 60),
                Event(MARINA, 8_000, start_s=90, duration_s=7 * 60),
                Event(FOXHILLS, 7_000, start_s=180, duration_s=8 * 60),
            ],
            budget_per_hour=3000,
            notes="Deliberately starved of budget.",
        ),
        Scenario(
            key="staggered_release", scheduled=[STADIUM],
            title="Staggered release, no danger",
            description="The same 12,000 people released over 40 minutes. Throughput stays "
                        "under the ramp's capacity throughout.",
            expect={STADIUM: False},
            events=[Event(STADIUM, 12_000, duration_s=40 * 60)],
            duration_s=60 * 60.0,
            notes="False-alarm test: busy but always draining.",
        ),
        Scenario(
            key="quiet_city",
            title="Quiet city, no event",
            description="Nobody is leaving anything. Any alarm here is purely invented.",
            expect={},
            events=[],
            duration_s=25 * 60.0,
            notes="False-alarm test: nothing is happening.",
        ),
        Scenario(
            key="low_penetration", scheduled=[STADIUM],
            title="Crush with only 5% app penetration",
            description="The same dangerous egress, but only 1,500 of 30,000 people have the "
                        "app. Tests whether a thin sample still detects, and whether the system "
                        "is honest when it cannot.",
            expect={STADIUM: True},
            pop=Population(app_share=0.05),
            events=[Event(STADIUM, 12_000, duration_s=12 * 60)],
        ),
        Scenario(
            key="devices_offline", scheduled=[STADIUM],
            title="Crush with 35% of devices unreachable",
            description="A dangerous egress during widespread loss of connectivity, which is "
                        "itself a symptom of overloaded cells in a crowd.",
            expect={STADIUM: True},
            pop=Population(unreachable_share=0.35),
            events=[Event(STADIUM, 12_000, duration_s=12 * 60)],
        ),
        Scenario(
            key="rate_limited", scheduled=[STADIUM, MARINA],
            title="Two crushes under a hard rate limit",
            description="Two simultaneous crushes with verification capped at 60 calls/min. "
                        "Forces the system to choose.",
            expect={STADIUM: True, MARINA: True},
            events=[
                Event(STADIUM, 12_000, start_s=0, duration_s=12 * 60),
                Event(MARINA, 9_000, start_s=120, duration_s=7 * 60),
            ],
            rate_limit={"location_verification": 60, "location_retrieval": 25},
        ),
    ]
