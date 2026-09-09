"""Aggregate the runs into the numbers that matter: precision, timing, cost."""
from __future__ import annotations
import json, statistics as st, sys


def main(path: str = "sim/out_results.json") -> None:
    d = json.load(open(path))
    runs = d["runs"]
    tp = fn = tn = fp = 0
    leads, errs, seg_ok, seg_n = [], [], 0, 0
    calls, naive = [], []
    per_scenario: dict[str, dict] = {}

    for r in runs:
        ps = per_scenario.setdefault(r["key"], {"n": 0, "tp": 0, "fn": 0, "fp": 0,
                                                "tn": 0, "calls": [], "leads": []})
        ps["n"] += 1
        ps["calls"].append(r["calls_total"])
        calls.append(r["calls_total"]); naive.append(r["naive_calls"])
        for zid, z in r["zones"].items():
            if z["expected_danger"]:
                if z["detected"]:
                    tp += 1; ps["tp"] += 1
                    if z["lead_s"] is not None:
                        leads.append(z["lead_s"]); ps["leads"].append(z["lead_s"])
                    if z["count_error_pct"] is not None:
                        errs.append(abs(z["count_error_pct"]))
                    if z["segment_correct"] is not None:
                        seg_n += 1; seg_ok += bool(z["segment_correct"])
                else:
                    fn += 1; ps["fn"] += 1
            else:
                if z["detected"]:
                    fp += 1; ps["fp"] += 1
                else:
                    tn += 1; ps["tn"] += 1

    print("=" * 74)
    print(f"{len(runs)} runs")
    print(f"  caught          {tp:3d}   missed        {fn:3d}   ->  sensitivity {100*tp/max(tp+fn,1):5.1f}%")
    print(f"  correct silence {tn:3d}   false alarms  {fp:3d}   ->  specificity {100*tn/max(tn+fp,1):5.1f}%")
    if leads:
        early = sum(1 for l in leads if l > 0)
        print(f"  warned in time  {early}/{len(leads)}   median lead {st.median(leads)/60:+.1f} min"
              f"   best {max(leads)/60:+.1f}  worst {min(leads)/60:+.1f}")
    if errs:
        print(f"  headcount error median {st.median(errs):.0f}%")
    if seg_n:
        print(f"  correct hazard segment {seg_ok}/{seg_n}")
    print(f"  calls median {st.median(calls):,.0f}  vs naive {st.median(naive):,.0f}"
          f"  ->  {st.median(naive)/max(st.median(calls),1):.1f}x cheaper")
    print("=" * 74)
    print(f"{'scenario':28} {'caught':>7} {'missed':>7} {'false':>6} {'calls':>7} {'lead min':>9}")
    for k, v in per_scenario.items():
        lead = f"{st.median(v['leads'])/60:+.1f}" if v["leads"] else "—"
        print(f"{k:28} {v['tp']:7d} {v['fn']:7d} {v['fp']:6d} {st.mean(v['calls']):7,.0f} {lead:>9}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sim/out_results.json")
