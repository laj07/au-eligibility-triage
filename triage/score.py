"""Turn findings into a 0-100 score, a three-tier action, and a record loader."""
from __future__ import annotations

import csv
from pathlib import Path

from .rules import Finding, check

GUIDE_AT = 10       # at or above: contact the registrant and help them fix it
ESCALATE_AT = 30    # at or above: send to a human reviewer (tuned in evaluate.py, see README)

ACTIONS = ("no_action", "educate_guide", "escalate_human_review")


def score(findings: list[Finding]) -> int:
    return min(100, sum(f.points for f in findings))


def action(s: int, guide_at: int = GUIDE_AT, escalate_at: int = ESCALATE_AT) -> str:
    if s >= escalate_at:
        return "escalate_human_review"
    if s >= guide_at:
        return "educate_guide"
    return "no_action"


def triage(rec: dict, guide_at: int = GUIDE_AT, escalate_at: int = ESCALATE_AT) -> dict:
    findings = check(rec)
    s = score(findings)
    return {
        "record_id": rec["record_id"],
        "score": s,
        "action": action(s, guide_at, escalate_at),
        "reasons": "; ".join(f"{f.code}: {f.reason}" for f in findings),
    }


def load_records(path: Path) -> list[dict]:
    recs = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            row["identifier_valid"] = row["identifier_valid"] == "1"
            row["tm_registered"] = row["tm_registered"] == "1"
            row["days_since_details_updated"] = int(row["days_since_details_updated"])
            row["domains_held"] = int(row["domains_held"])
            recs.append(row)
    return recs
