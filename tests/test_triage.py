"""Run from the repo root:  python tests/test_triage.py   (or: python -m pytest tests -q)"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from triage.rules import ALLOWED, check, name_connection  # noqa: E402
from triage.score import ACTIONS, action, load_records, score, triage  # noqa: E402


def base_rec(**kw) -> dict:
    rec = {
        "record_id": "T1", "namespace": "com.au", "entity_type": "company",
        "legal_name": "Harbour Plumbing Pty Ltd", "activity": "plumbing repairs",
        "requested_name": "harbourplumbing", "identifier_valid": True, "registry_status": "active",
        "tm_registered": False, "days_since_details_updated": 30, "domains_held": 1,
    }
    rec.update(kw)
    return rec


def codes(rec):
    return {f.code for f in check(rec)}


def test_clean_record_has_no_findings():
    assert check(base_rec()) == []
    assert score(check(base_rec())) == 0


def test_name_connection_types():
    n = "Harbour Plumbing Pty Ltd"
    assert name_connection("harbourplumbing", n, "") == "exact"
    assert name_connection("harbour", n, "") == "exact"          # one of the words, in order
    assert name_connection("plumbingharbour", n, "") != "exact"  # wrong order is not exact
    assert name_connection("hp", n, "") == "acronym"
    assert name_connection("harbplu", n, "") == "abbreviation"
    assert name_connection("bestplumbingdeals", n, "plumbing repairs") == "activity"
    assert name_connection("cheapflights", n, "plumbing repairs") == "none"


def test_trading_as_checks_both_parts():
    n = "Alex Marlow trading as Wattle Bakery"
    assert name_connection("wattlebakery", n, "") == "exact"
    assert name_connection("alexmarlow", n, "") == "exact"


def test_each_rule_fires_on_its_own():
    assert "ID_INVALID" in codes(base_rec(identifier_valid=False))
    assert "REGISTRY_CANCELLED" in codes(base_rec(registry_status="cancelled"))
    assert "REGISTRY_PENDING" in codes(base_rec(registry_status="pending"))
    assert "ENTITY_NAMESPACE_MISMATCH" in codes(base_rec(namespace="id.au"))
    assert "TM_NOT_REGISTERED" in codes(base_rec(entity_type="trade_mark_holder", tm_registered=False))
    assert "NAME_UNRELATED" in codes(base_rec(requested_name="cryptoinvest"))
    assert "STALE_DETAILS" in codes(base_rec(days_since_details_updated=500))
    assert "BULK_HOLDER" in codes(base_rec(domains_held=20))
    assert "BULK_SPECULATIVE" in codes(base_rec(domains_held=20, requested_name="vapeshop"))


def test_score_is_capped_and_tiers_are_ordered():
    bad = base_rec(identifier_valid=False, registry_status="cancelled", requested_name="vapeshop")
    assert score(check(bad)) == 100
    assert action(0) == "no_action"
    assert action(15) == "educate_guide"
    assert action(60) == "escalate_human_review"
    assert [action(s) for s in range(0, 101)] == sorted((action(s) for s in range(0, 101)), key=ACTIONS.index)


def test_every_reason_is_explained():
    out = triage(base_rec(identifier_valid=False))
    assert out["reasons"].startswith("ID_INVALID:")


def test_namespaces_cover_every_entity_type_used():
    used = {"company", "business_name", "sole_trader", "partnership", "inc_assoc", "trade_mark_holder",
            "charity", "nonprofit", "club", "individual"}
    allowed = set().union(*ALLOWED.values())
    assert used <= allowed


def test_generator_is_deterministic_and_rules_never_see_truth():
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic.py")], check=True, capture_output=True)
    a = (ROOT / "data" / "registrations.csv").read_text()
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic.py")], check=True, capture_output=True)
    assert a == (ROOT / "data" / "registrations.csv").read_text()
    assert "truth" not in a.splitlines()[0] and "failure_mode" not in a.splitlines()[0]
    assert len(load_records(ROOT / "data" / "registrations.csv")) == 600


def test_catches_most_rule_visible_cases_and_misses_subtle_ones():
    import csv
    from evaluate import load_truth  # noqa: E402
    truth = load_truth()
    rows = [triage(r) for r in load_records(ROOT / "data" / "registrations.csv")]
    esc = {r["record_id"] for r in rows if r["action"] == "escalate_human_review"}
    visible = [t for t in truth.values() if t["truth_ineligible"] == "1" and t["failure_mode"] != "subtle"]
    subtle = [t for t in truth.values() if t["failure_mode"] == "subtle"]
    assert sum(t["record_id"] in esc for t in visible) / len(visible) > 0.9
    assert sum(t["record_id"] in esc for t in subtle) == 0   # the rules cannot see these, by design


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
