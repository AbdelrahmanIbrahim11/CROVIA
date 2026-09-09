# Simulation results

30 runs · 10 scenarios · 3 seeds each · Lusail, 30,000 people, 10,000 with the app

The engine under test is the real backend engine in `app/`. It reads nothing
from the twin — only a CAMARA layer carrying the network's real limits — so
these numbers are not circular.

## Headline

| | |
|---|---|
| Dangerous crowds caught | **33 / 33** (100%) |
| Correct silence on safe crowds | **117 / 117** (100%) |
| False alarms | **0** |
| Warned before it became dangerous | **31 / 33** |
| Median warning time | **+8.9 minutes** |
| Correct hazard link named | **33 / 33** |
| API calls, median per run | 1,890 vs 14,130 naive — **7.5× cheaper** |
| Headcount error, median | **20%** |

Half the scenarios contain no danger at all, including one with the *same*
crowd size as the crush and only the gate width changed.

## Per scenario

| Scenario | Caught | Missed | False | Calls | Lead |
|---|---|---|---|---|---|
| single_crush | 3 | 0 | 0 | 1,885 | +9.0 min |
| single_safe | — | — | 0 | 1,425 | — |
| two_crowds_both_dangerous | 6 | 0 | 0 | 2,620 | +7.8 min |
| two_crowds_one_safe | 3 | 0 | 0 | 2,220 | +9.0 min |
| three_crowds | 9 | 0 | 0 | 2,995 | +4.7 min |
| staggered_release | — | — | 0 | 1,760 | — |
| quiet_city | — | — | 0 | 480 | — |
| low_penetration (5% app) | 3 | 0 | 0 | 2,100 | +9.0 min |
| devices_offline (35%) | 3 | 0 | 0 | 1,850 | +9.0 min |
| rate_limited | 6 | 0 | 0 | 1,785 | +7.8 min |

## What produced the warning time

The earlier study warned a median of **19 minutes late**. The fix was not
better thresholds — it was noticing that a scheduled crowd can be judged
before it moves.

For a fixture, two numbers are already known: how many people are expected over
what period, and how many the narrowest link can pass. 12,000 people over 12
minutes is about 1,000/min against a 9 m ramp that passes about 650/min. That
comparison costs **no API calls at all** and is available before the first
person leaves their seat.

It is a prediction, not a measurement, so it never fires alone. It lowers the
bar for confirming: a predicted crowd does not have to re-prove that it is a
crowd, only that it is actually filling. That is what recovered the timing.

The same rule keeps the safe cases silent, which is the real test:

* `single_safe` — same 12,000 people, gates 3× wider. 1,000/min against
  1,944/min capacity, so no prediction, and no alarm.
* `staggered_release` — same 12,000 people over 40 minutes. 300/min against
  650/min, so no prediction, and no alarm.

## Cost: what the sweep showed

| Setting | Caught | False alarms | Calls |
|---|---|---|---|
| cheap | 100% | 1 | 1,872 |
| **balanced** | **100%** | **0** | **1,958** |
| precise | 100% | 1 | 2,385 |

Spending more is not simply better. The most aggressive setting samples
marginal situations often enough to talk itself into a false alarm, at 22% more
cost. Balanced is the default.

## Honest limits

* **Headcount error is 20%.** The number of people is published as a band, and
  the alarm never depends on it alone.
* **Two of 33 detections still arrived late**, both in the three-crowd run where
  budget was deliberately starved.
* **The twin is not Lusail.** District and landmark anchors are real; the
  corridors are a modelled city, not the OpenStreetMap walkable graph.
* **Nokia's pricing is unknown.** Call counts are measured; money is not.
* **The sandbox cannot move a device**, so the geofence-crossing path is exercised
  here but cannot be demonstrated live. Counting works either way, which is why
  it is the main sensor.

## Reproduce

```bash
cd backend
PYTHONPATH=. python3 sim/run.py      # all scenarios, writes sim/out_results.json
PYTHONPATH=. python3 sim/report.py   # the table above
PYTHONPATH=. python3 sim/sweep.py    # precision against cost
```
