"""
The tools the agent may call.

These keep the names from the LangGraph notebook — arm_chokepoints,
verify_and_filter, retrieve_locations_batch — so that work carries straight
over. What changes is the bodies. In the notebook each one returned a fixed
string ("Net accumulation is +45 people/min"), which is fine for designing a
graph and tells you nothing about a real crowd. Each now performs the actual
step against the live engine and reports what really happened.

The boundary that must not move: these tools GATHER EVIDENCE and SPEND MONEY.
None of them decides whether anyone is in danger. That verdict comes from
detect.danger.assess(), which is deterministic, because after an incident
somebody will ask why the alarm fired, or worse why it did not, and the answer
has to be a rule a person can check by hand.
"""

from __future__ import annotations

from app.camara.client import ApiError, Area
from app.core.city import city
from app.detect.danger import Evidence, assess


def arm_chokepoints(engine, zone_id: str) -> dict:
    """
    Start watching a chokepoint and report what is known about it.

    Returns the zone's capacity from the city plan, which needs no measurement,
    and the fill rate if enough counts have been taken to have one.
    """
    if zone_id not in city.zones:
        return {"error": f"unknown zone {zone_id}"}
    zs = engine.zones[zone_id]
    hazard = city.bottleneck_of(zone_id)
    capacity = city.zone_capacity_per_min(zone_id)
    district = city.zones[zone_id].district_id
    engine.districts[district].state = "WATCHING"
    return {
        "zone_id": zone_id,
        "narrowest_link_m": hazard.width_m if hazard else None,
        "capacity_per_min": round(capacity),
        "fill_rate_per_min": round(zs.rate_per_min()),
        "counts_taken": len(zs.counts),
        "note": "capacity comes from the city plan and costs nothing to know",
    }


def verify_and_filter(engine, zone_id: str, max_calls: int = 45) -> dict:
    """
    Count how many people are inside, using Location Verification.

    This is the main sensor. It needs no subscription and returns no
    coordinates, and it works even though sandbox devices never move, which is
    why it replaced counting geofence crossings.
    """
    if zone_id not in city.zones:
        return {"error": f"unknown zone {zone_id}"}
    people, inside, checked = engine.count_zone(zone_id, max_calls)
    if checked == 0:
        return {"error": "no panel devices answered", "checked": 0}
    engine.zones[zone_id].counts.append((engine.now, people))
    return {
        "zone_id": zone_id,
        "panel_inside": inside,
        "panel_checked": checked,
        "people_estimate": round(people),
        "calls_spent": checked,
        "note": "the panel is a uniform sample of the city, so this is unbiased",
    }


def retrieve_locations_batch(engine, zone_id: str, batch_size: int = 10) -> dict:
    """
    Fetch real positions for a small batch, filtering out unreachable devices.

    The most expensive call in the system, so it runs last and on a sample. An
    unreachable device cannot be located at all, so those are dropped first
    rather than paid for and discarded.
    """
    if zone_id not in city.zones:
        return {"error": f"unknown zone {zone_id}"}
    z = city.zones[zone_id]
    area = Area(z.center.lat, z.center.lon, z.radius_m)
    panel = engine.registry.panel_members()[: batch_size * 3]

    reachable, fixes, unknown = [], [], 0
    for hashed in panel:
        if len(fixes) >= batch_size:
            break
        phone = engine.registry.vault.phone_for(hashed)
        if not phone:
            continue
        try:
            if not engine.client.get_reachability(phone, z.district_id)["reachable"]:
                continue
            reachable.append(phone)
            r = engine.client.retrieve_location(phone, 90, z.district_id)
        except ApiError:
            continue
        if r.get("status") == "OK":
            fixes.append(r)
        else:
            unknown += 1

    return {
        "zone_id": zone_id,
        "reachable_checked": len(reachable),
        "fixes": len(fixes),
        "unknown": unknown,
        "median_accuracy_m": (
            round(sorted(f["radius_m"] for f in fixes)[len(fixes) // 2])
            if fixes
            else None
        ),
        "note": "UNKNOWN is a normal answer, not an ebatch_sizerror",
    }


def judge(engine, zone_id: str) -> dict:
    """
    The verdict. Deterministic on purpose — the agent may not decide this.

    The agent chooses where to look and what to spend. Whether people are in
    danger is decided by a rule, so it can be audited afterwards.
    """
    if zone_id not in city.zones:
        return {"error": f"unknown zone {zone_id}"}
    zs = engine.zones[zone_id]
    people = zs.counts[-1][1] if zs.counts else 0.0
    v = assess(
        city,
        Evidence(
            zone_id=zone_id,
            people=people,
            people_rate_per_min=zs.rate_per_min(),
            inside_sampled=len(zs.counts),
            sustained_s=(
                0.0 if zs.filling_since is None else engine.now - zs.filling_since
            ),
        ),
    )
    return v.to_dict()


TOOL_SPECS = [
    {
        "name": "arm_chokepoints",
        "description": "Start watching a chokepoint. Returns its capacity from the city plan "
        "and the current fill rate. Cheap. Call this first.",
        "args": {"zone_id": "str"},
    },
    {
        "name": "verify_and_filter",
        "description": "Count how many people are inside the zone using Location Verification. "
        "Moderate cost. Call this when a zone looks worth investigating.",
        "args": {"zone_id": "str", "max_calls": "int"},
    },
    {
        "name": "retrieve_locations_batch",
        "description": "Fetch real positions for a small batch of devices. Most expensive. "
        "Only call this after counting shows the crowd is growing.",
        "args": {"zone_id": "str", "batch_size": "int"},
    },
    {
        "name": "judge",
        "description": "Ask the deterministic rules whether this zone is dangerous. Free. "
        "You do not decide this yourself.",
        "args": {"zone_id": "str"},
    },
]
