"""
Generate SYNTHETIC registration records with hidden ground truth.

Nothing here is real registrant data. Business names are made up from word lists; any resemblance
to a real business is coincidence. The ground truth is written to a separate file (truth.csv) so the
rules never see it.

Some ineligible records are deliberately "subtle" (nothing for the rules to catch), and some eligible
records deliberately look odd (stale details, loose names, pending registration). Real data is messy
in the same way, so the rules should make mistakes in both directions.

Run from the repo root:  python data/generate_synthetic.py
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 20261029
N = 600
P_INELIGIBLE = 0.12
P_SUBTLE = 0.25         # share of ineligible records with no visible signal
P_ODD_ELIGIBLE = 0.12   # share of eligible records that look odd

ROOT = Path(__file__).resolve().parent
FIRST = ["Harbour", "Wattle", "Granite", "Saltbush", "Coral", "Ironbark", "Lantern", "Meridian",
         "Kestrel", "Banksia", "Tidewater", "Cedar", "Summit", "Bluegum", "Northgate", "Riverbend",
         "Bellbird", "Quarry", "Fernhill", "Oakridge"]
INDUSTRY = [("Plumbing", "plumbing repairs"), ("Bakery", "bakery cakes bread"),
            ("Accounting", "accounting tax bookkeeping"), ("Landscaping", "landscaping gardens"),
            ("Physio", "physiotherapy rehabilitation"), ("Cycles", "bicycle repairs cycling"),
            ("Printing", "printing signage"), ("Consulting", "business consulting"),
            ("Electrical", "electrical wiring"), ("Tutoring", "tutoring education")]
PEOPLE = [("Alex", "Marlow"), ("Priya", "Nandakumar"), ("Sam", "Okafor"), ("Jess", "Whitlam"),
          ("Chen", "Liu"), ("Mia", "Fitzgerald"), ("Tom", "Haddad"), ("Ella", "Burrows")]
SPECULATIVE = ["bestdeals", "cheapflights", "vapeshop", "loansnow", "casinoplay", "cryptoinvest"]

COMMERCIAL = ["company", "business_name", "sole_trader", "partnership", "inc_assoc"]
NONPROFIT = ["inc_assoc", "charity", "nonprofit", "club"]

rng = random.Random(SEED)


def legal_name(entity: str, first: str, industry: str, person) -> str:
    if entity == "individual":
        return f"{person[0]} {person[1]}"
    if entity in ("inc_assoc", "charity", "nonprofit", "club"):
        return f"{first} {industry} Association Inc"
    if entity == "sole_trader":
        return f"{person[0]} {person[1]} trading as {first} {industry}"
    return f"{first} {industry} Pty Ltd"


def good_requested(entity, first, industry, person, activity, kind=None):
    if entity == "individual":
        return f"{person[0]}{person[1]}".lower()
    kind = kind or rng.choice(["exact", "exact", "acronym", "activity", "abbrev"])
    if kind == "exact":
        return rng.choice([f"{first}{industry}", f"{first}"]).lower()
    if kind == "acronym":
        return (first[0] + industry[0]).lower()
    if kind == "activity":
        return f"{first[:4]}{rng.choice(activity.split())}".lower()
    return f"{first}{industry[:3]}".lower()


def make(i: int) -> tuple[dict, dict]:
    first = rng.choice(FIRST)
    industry, activity = rng.choice(INDUSTRY)
    person = rng.choice(PEOPLE)
    ineligible = rng.random() < P_INELIGIBLE
    mode = "none"

    ns = rng.choices(["com.au", "net.au", "org.au", "asn.au", "id.au"], [55, 8, 20, 4, 13])[0]
    if ns == "id.au":
        entity = "individual"
    elif ns in ("org.au", "asn.au"):
        entity = rng.choice(NONPROFIT)
    else:
        entity = rng.choices(COMMERCIAL + ["trade_mark_holder"], [40, 20, 15, 5, 5, 15])[0]

    rec = {
        "record_id": f"R{i:04d}", "namespace": ns, "entity_type": entity,
        "legal_name": legal_name(entity, first, industry, person), "activity": activity,
        "requested_name": good_requested(entity, first, industry, person, activity),
        "identifier_valid": 1, "registry_status": "active",
        "tm_registered": 1 if entity == "trade_mark_holder" else "",
        "days_since_details_updated": rng.randint(5, 350), "domains_held": rng.choice([1, 1, 1, 2, 3, 5]),
    }
    if entity == "trade_mark_holder":
        rec["legal_name"] = f"{first} {industry} Pty Ltd"
        rec["requested_name"] = f"{first}{industry}".lower()

    if ineligible:
        if rng.random() < P_SUBTLE:
            mode = "subtle"   # eligible-looking on paper; the rules cannot see the problem
        else:
            mode = rng.choice(["invalid_id", "cancelled", "mismatch", "unrelated", "tm_pending", "speculative_bulk"])
            if mode == "invalid_id":
                rec["identifier_valid"] = 0
            elif mode == "cancelled":
                rec["registry_status"] = "cancelled"
            elif mode == "mismatch":
                rec["namespace"] = "id.au" if ns != "id.au" else "org.au"
                if rec["namespace"] == "org.au":
                    rec["entity_type"] = "individual"
            elif mode == "unrelated":
                rec["requested_name"] = rng.choice(SPECULATIVE)
            elif mode == "tm_pending":
                rec["entity_type"] = "trade_mark_holder"
                rec["namespace"] = "com.au"
                rec["tm_registered"] = 0
                rec["requested_name"] = f"{first}{industry}".lower()
            else:
                rec["requested_name"] = rng.choice(SPECULATIVE)
                rec["domains_held"] = rng.randint(15, 60)
                rec["days_since_details_updated"] = rng.randint(300, 900)
    elif rng.random() < P_ODD_ELIGIBLE:
        odd = rng.choice(["stale", "pending", "loose_name", "big_holder"])
        if odd == "stale":
            rec["days_since_details_updated"] = rng.randint(401, 900)
        elif odd == "pending":
            rec["registry_status"] = "pending"
        elif odd == "loose_name":
            rec["requested_name"] = f"{first[:2]}{industry[:2]}".lower() + "hub"
        else:
            rec["domains_held"] = rng.randint(15, 40)

    truth = {"record_id": rec["record_id"], "truth_ineligible": int(ineligible), "failure_mode": mode}
    return rec, truth


def main() -> None:
    recs, truths = zip(*(make(i) for i in range(1, N + 1)))
    fields = list(recs[0].keys())
    with open(ROOT / "registrations.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(recs)
    with open(ROOT / "truth.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["record_id", "truth_ineligible", "failure_mode"])
        w.writeheader()
        w.writerows(truths)
    n_bad = sum(t["truth_ineligible"] for t in truths)
    print(f"wrote {N} records, {n_bad} ineligible ({n_bad / N:.1%})")


if __name__ == "__main__":
    main()
