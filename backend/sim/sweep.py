"""
Sweep the sample size and report precision against cost.

Each counted device stands for population/sample people, so the sample size
sets the noise floor on every number the danger rules see. Threshold tuning
cannot get below that floor, so the honest question is how much precision a
given amount of spend buys.
"""
from __future__ import annotations
import json, statistics as st, sys

from app.detect.engine import ALERT, CONFIRMING, IDLE, STANDDOWN, WATCHING, Engine
from sim.run import run
from sim.scenarios import all_scenarios

SETTINGS = {
    "cheap":    {IDLE: (300.0, 22), WATCHING: (120.0, 45), CONFIRMING: (60.0, 60),
                 ALERT: (60.0, 60), STANDDOWN: (300.0, 22)},
    "balanced": {IDLE: (300.0, 30), WATCHING: (90.0, 80), CONFIRMING: (60.0, 110),
                 ALERT: (60.0, 110), STANDDOWN: (300.0, 30)},
    "precise":  {IDLE: (240.0, 40), WATCHING: (60.0, 130), CONFIRMING: (45.0, 180),
                 ALERT: (45.0, 180), STANDDOWN: (240.0, 40)},
}


def score(seeds=(0, 1, 2)) -> dict:
    tp = fn = tn = fp = 0
    leads, calls, errs, seg_ok, seg_n = [], [], [], 0, 0
    for sc in all_scenarios():
        for s in seeds:
            fresh = [x for x in all_scenarios() if x.key == sc.key][0]
            r = run(fresh, seed=s, keep_trace=False)
            calls.append(r.calls_total)
            for z in r.zones.values():
                if z["expected_danger"]:
                    if z["detected"]:
                        tp += 1
                        if z["lead_s"] is not None:
                            leads.append(z["lead_s"])
                        if z["count_error_pct"] is not None:
                            errs.append(abs(z["count_error_pct"]))
                        if z["segment_correct"] is not None:
                            seg_n += 1; seg_ok += bool(z["segment_correct"])
                    else:
                        fn += 1
                else:
                    tn += 1 if not z["detected"] else 0
                    fp += 1 if z["detected"] else 0
    return {
        "sensitivity": 100 * tp / max(tp + fn, 1),
        "specificity": 100 * tn / max(tn + fp, 1),
        "tp": tp, "fn": fn, "fp": fp,
        "in_time": sum(1 for l in leads if l > 0), "n_lead": len(leads),
        "median_lead_min": (st.median(leads) / 60) if leads else None,
        "count_err_pct": (st.median(errs)) if errs else None,
        "segment": f"{seg_ok}/{seg_n}",
        "calls": st.median(calls),
    }


def main() -> None:
    out = {}
    for name, cadence in SETTINGS.items():
        Engine.CADENCE = cadence
        r = score()
        out[name] = r
        lead = "—" if r["median_lead_min"] is None else f"{r['median_lead_min']:+.1f}"
        print(f"{name:9} sens {r['sensitivity']:5.1f}%  spec {r['specificity']:5.1f}%  "
              f"false {r['fp']:2d}  in-time {r['in_time']}/{r['n_lead']}  lead {lead:>5} min  "
              f"count err {r['count_err_pct'] or 0:4.0f}%  seg {r['segment']:6}  "
              f"calls {r['calls']:,.0f}", flush=True)
    json.dump(out, open("sim/out_sweep.json", "w"), indent=1)


if __name__ == "__main__":
    print(f"{'setting':9} {'precision and cost':^100}")
    main()
