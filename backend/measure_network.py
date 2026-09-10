"""
How fast is the real network, and does our sampling plan survive it?

The engine samples up to 110 devices inside one 60-second cycle, and it does so
ONE CALL AT A TIME. That is fine at the speeds the simulated city returns, and
it is a guess against a real network. If a single call takes two seconds, 110 of
them take nearly four minutes, the 60-second cadence is missed on every cycle,
and the fill rate is measured over the wrong window - which is the number the
whole alarm rests on.

This measures three things that decide whether the plan holds:

    how long one call really takes, at the median and at the slow end
    whether asking several at once helps, and how much
    how often the network answers UNKNOWN rather than yes or no

Nokia's own limits arrive in the response headers - 100 calls a second and
1500 a minute at the time of writing - so the question is never "are we allowed
to" but "are we fast enough".

    NOKIA_NAC_API_KEY=... PYTHONPATH=. ./venv/bin/python measure_network.py
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import app.config  # noqa: F401  - loads .env
from app.camara.client import Area, NokiaClient

# Deliberately small. This spends real calls, and thirty is enough to see a
# median and a slow tail without burning quota that a demo might need.
SAMPLES = 30
CONCURRENCY = 10

# The zone the engine actually watches hardest, so the numbers describe the
# real case rather than an easier one.
ZONE = Area(25.4240, 51.4904, 600)

# Nokia's four test numbers, cycled through. Using one number repeatedly could
# be answered from a cache and would flatter the result.
NUMBERS = ["+99999991000", "+99999991001", "+99999991002", "+99999991003"]

# What the engine asks for at its busiest, and how long it has to do it in.
PEAK_CALLS = 110
CADENCE_S = 60


def one_call(client: NokiaClient, phone: str) -> tuple[float, str]:
    start = time.perf_counter()
    try:
        r = client.verify_location(phone, ZONE)
        return time.perf_counter() - start, r["verification_result"]
    except Exception as exc:
        return time.perf_counter() - start, f"ERROR {type(exc).__name__}"


def summarise(name: str, times: list[float]) -> float:
    times = sorted(times)
    p50 = statistics.median(times)
    p95 = times[int(len(times) * 0.95) - 1]
    print(f"  {name}")
    print(f"    median {p50*1000:7.0f} ms")
    print(f"    p95    {p95*1000:7.0f} ms")
    print(f"    worst  {times[-1]*1000:7.0f} ms")
    return p50


def main() -> int:
    key = os.getenv("NOKIA_NAC_API_KEY", "").strip()
    if not key:
        print("NOKIA_NAC_API_KEY is not set - nothing to measure.")
        return 1

    client = NokiaClient(api_key=key)
    print("=" * 66)
    print("How fast is Nokia, and does our sampling plan fit inside it?")
    print("=" * 66)
    print(f"\nasking {SAMPLES} times, one after another...\n")

    seq_times, results = [], []
    for i in range(SAMPLES):
        dt, res = one_call(client, NUMBERS[i % len(NUMBERS)])
        seq_times.append(dt)
        results.append(res)
    seq_median = summarise("one at a time", seq_times)

    print(f"\nasking {SAMPLES} times, {CONCURRENCY} at once...\n")
    par_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        par = list(pool.map(lambda i: one_call(client, NUMBERS[i % len(NUMBERS)]),
                            range(SAMPLES)))
    par_wall = time.perf_counter() - par_start
    summarise(f"{CONCURRENCY} at once", [t for t, _ in par])
    print(f"    {SAMPLES} calls finished in {par_wall:.1f} s wall clock")

    print("\nwhat the network answered\n")
    for value in sorted(set(results)):
        n = results.count(value)
        print(f"    {value:<12} {n:>3}  ({n/len(results):.0%})")
    unknown = results.count("UNKNOWN") / len(results)

    # --- does the plan hold? ------------------------------------------------
    print("\n" + "=" * 66)
    print("Does the engine's busiest cycle fit?")
    print("=" * 66)
    seq_total = seq_median * PEAK_CALLS
    per_call_parallel = par_wall / SAMPLES
    par_total = per_call_parallel * PEAK_CALLS

    print(f"\n  the engine asks for {PEAK_CALLS} counts every {CADENCE_S} s\n")
    print(f"    one at a time      {seq_total:6.1f} s   "
          f"{'FITS' if seq_total <= CADENCE_S else 'TOO SLOW'}")
    print(f"    {CONCURRENCY} at once        {par_total:6.1f} s   "
          f"{'FITS' if par_total <= CADENCE_S else 'TOO SLOW'}")

    if seq_total > CADENCE_S:
        need = seq_total / CADENCE_S
        print(f"\n  Sampling one at a time misses the cadence. Asking about")
        print(f"  {need:.0f} at once would bring it inside {CADENCE_S} s, and Nokia's")
        print(f"  limit of 100 calls a second leaves plenty of room for that.")
    else:
        print("\n  One at a time is fast enough. No change needed.")

    if unknown > 0.2:
        print(f"\n  {unknown:.0%} of answers were UNKNOWN. Each one is a device that")
        print("  cost a call and counted for nothing, so the usable sample is")
        print("  smaller than the sample size suggests.")

    print(f"\n  calls spent: {client.ledger.summary()['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
