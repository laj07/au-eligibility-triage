"""
Evaluate the triage on the synthetic set and tune the escalation cutoff by expected cost.

Cost model (assumptions, change them and re-run):
  c_fp   = cost of sending an eligible registrant to human review (reviewer time, friction)
  c_miss = cost of letting an ineligible registration through unreviewed
The cutoff that minimises total cost is picked from the labelled data. As a cross-check, near the
best cutoff the share of ineligible records should be roughly c_fp / (c_fp + c_miss), the textbook
decision threshold.

Run from the repo root:  python evaluate.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from triage.score import GUIDE_AT, ESCALATE_AT, load_records, triage  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

C_FP, C_MISS = 1.0, 5.0


def load_truth() -> dict[str, dict]:
    with open(ROOT / "data" / "truth.csv", newline="") as f:
        return {r["record_id"]: r for r in csv.DictReader(f)}


def confusion(rows, truth, cutoff):
    tp = fp = fn = tn = 0
    for r in rows:
        bad = truth[r["record_id"]]["truth_ineligible"] == "1"
        flagged = r["score"] >= cutoff
        tp += bad and flagged
        fp += (not bad) and flagged
        fn += bad and (not flagged)
        tn += (not bad) and (not flagged)
    return tp, fp, fn, tn


def main() -> None:
    recs = load_records(ROOT / "data" / "registrations.csv")
    truth = load_truth()
    rows = [triage(r) for r in recs]
    with open(OUT / "triaged.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    n_bad = sum(truth[r["record_id"]]["truth_ineligible"] == "1" for r in rows)

    cutoffs = list(range(0, 101, 5))
    costs, table = [], []
    for c in cutoffs:
        tp, fp, fn, tn = confusion(rows, truth, c)
        cost = C_FP * fp + C_MISS * fn
        costs.append(cost)
        table.append({"cutoff": c, "flagged": tp + fp, "precision": tp / (tp + fp) if tp + fp else None,
                      "recall": tp / (tp + fn) if tp + fn else None, "cost": cost})
    best = min(table, key=lambda t: (t["cost"], -t["cutoff"]))

    # cross-check: share of ineligible records among those scoring in a window around the best cutoff
    lo, hi = max(0, best["cutoff"] - 10), best["cutoff"] + 10
    window = [r for r in rows if lo <= r["score"] < hi]
    share_bad = (sum(truth[r["record_id"]]["truth_ineligible"] == "1" for r in window) / len(window)) if window else None
    theory = C_FP / (C_FP + C_MISS)

    tp, fp, fn, tn = confusion(rows, truth, ESCALATE_AT)
    by_mode = {}
    for r in rows:
        t = truth[r["record_id"]]
        if t["truth_ineligible"] == "1":
            m = by_mode.setdefault(t["failure_mode"], {"n": 0, "escalated": 0})
            m["n"] += 1
            m["escalated"] += r["score"] >= ESCALATE_AT
    tiers = {a: sum(r["action"] == a for r in rows) for a in ("no_action", "educate_guide", "escalate_human_review")}

    summary = {
        "records": n, "ineligible": n_bad, "costs_assumed": {"c_fp": C_FP, "c_miss": C_MISS},
        "default_escalate_at": ESCALATE_AT, "default_guide_at": GUIDE_AT,
        "at_default": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                       "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None},
        "best_cutoff_by_cost": best, "theory_threshold_c_fp_over_sum": theory,
        "ineligible_share_near_best_cutoff": share_bad, "tiers": tiers, "missed_by_mode": by_mode,
    }
    (OUT / "metrics.json").write_text(json.dumps(summary, indent=2, default=float))

    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.plot(cutoffs, costs, color="#2a78d6", lw=2)
    ax.axvline(best["cutoff"], color="#eb6834", lw=1.4)
    ax.set_xlabel("Escalate when score is at least")
    ax.set_ylabel(f"Expected cost (c_fp={C_FP:g}, c_miss={C_MISS:g})")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Cost of the escalation cutoff on synthetic data", fontsize=9, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "cost_curve.png", dpi=200)

    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
