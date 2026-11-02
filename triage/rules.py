"""
Rule checks for a registration record. Every rule returns a Finding with a code, points and a
plain-language reason, so a reviewer can see WHY a record was flagged.

These rules are a simplified, illustrative model of eligibility and name-connection checks.
They are NOT auDA's rules or system. Check anything real against the current .au Licensing Rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LEGAL_NOISE = {"pty", "ltd", "limited", "inc", "incorporated", "association", "co", "company", "the", "and", "of"}

# Which entity types may hold which namespace (simplified).
ALLOWED = {
    "com.au": {"company", "business_name", "sole_trader", "partnership", "foreign_company",
               "trade_mark_holder", "inc_assoc", "statutory_body"},
    "net.au": {"company", "business_name", "sole_trader", "partnership", "foreign_company",
               "trade_mark_holder", "inc_assoc", "statutory_body"},
    "org.au": {"inc_assoc", "political_party", "union", "club", "charity", "nonprofit"},
    "asn.au": {"inc_assoc", "political_party", "union", "club", "charity", "nonprofit"},
    "id.au": {"individual"},
}

# Words that suggest registering a name for resale or speculation rather than use.
SPECULATIVE_TERMS = ("bestdeals", "cheapflights", "vapeshop", "loansnow", "casinoplay", "cryptoinvest")

BULK_THRESHOLD = 15  # domains held by one registrant before the pattern is worth a look
STALE_DAYS = 400     # details not updated for this long, at renewal


@dataclass(frozen=True)
class Finding:
    code: str
    points: int
    reason: str


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_subsequence(small: str, big: str) -> bool:
    it = iter(big)
    return all(ch in it for ch in small)


def name_connection(requested: str, legal_name: str, activity: str) -> str:
    """Return how the requested name relates to the registrant: exact, acronym, abbreviation,
    activity or none."""
    # a sole trader "X trading as Y" may link the name to either part
    parts = [p for p in re.split(r"\s+trading as\s+", legal_name.lower()) if p.strip()]
    best = "none"
    for part in parts:
        rank = _connection_to(requested, part, activity)
        if _ORDER[rank] > _ORDER[best]:
            best = rank
    return best


_ORDER = {"none": 0, "activity": 1, "abbreviation": 2, "acronym": 3, "exact": 4}


def _connection_to(requested: str, legal_name: str, activity: str) -> str:
    words = [t for t in tokens(legal_name) if t not in LEGAL_NOISE]
    req = squash(requested)
    if not words or not req:
        return "none"
    # exact: matches one or more consecutive words of the legal name, in order
    for i in range(len(words)):
        for j in range(i + 1, len(words) + 1):
            if "".join(words[i:j]) == req:
                return "exact"
    # acronym: initial letters of each word
    if len(words) >= 2 and req == "".join(w[0] for w in words):
        return "acronym"
    # abbreviation: letters of the name in order, same first letter, covers a fair share of it
    joined = "".join(words)
    if len(req) >= 3 and req[0] == joined[0] and _is_subsequence(req, joined) and len(req) / len(joined) >= 0.4:
        return "abbreviation"
    # activity: the name refers to something the registrant does
    for w in tokens(activity):
        if len(w) >= 4 and w in req:
            return "activity"
    return "none"


def check(rec: dict) -> list[Finding]:
    out: list[Finding] = []

    if not rec["identifier_valid"]:
        out.append(Finding("ID_INVALID", 45, "Identifier (ABN/ACN/association number) did not verify"))

    status = rec["registry_status"]
    if status == "cancelled":
        out.append(Finding("REGISTRY_CANCELLED", 45, "The registrant's registration is cancelled"))
    elif status == "pending":
        out.append(Finding("REGISTRY_PENDING", 20, "The registrant's registration is still pending"))

    if rec["entity_type"] not in ALLOWED.get(rec["namespace"], set()):
        out.append(Finding("ENTITY_NAMESPACE_MISMATCH", 35,
                           f"{rec['entity_type']} is not an expected holder of {rec['namespace']}"))

    if rec["entity_type"] == "trade_mark_holder" and not rec["tm_registered"]:
        out.append(Finding("TM_NOT_REGISTERED", 30, "Eligibility rests on a trade mark that is filed, not registered"))

    link = name_connection(rec["requested_name"], rec["legal_name"], rec["activity"])
    if link == "none":
        out.append(Finding("NAME_UNRELATED", 30, "Requested name has no visible link to the registrant"))
    elif link == "abbreviation":
        out.append(Finding("NAME_WEAK_LINK", 8, "Name is only a loose abbreviation of the registrant's name"))

    speculative = any(t in squash(rec["requested_name"]) for t in SPECULATIVE_TERMS)
    if rec["domains_held"] >= BULK_THRESHOLD and speculative:
        out.append(Finding("BULK_SPECULATIVE", 25, "Many domains held and the name looks speculative"))
    elif rec["domains_held"] >= BULK_THRESHOLD:
        out.append(Finding("BULK_HOLDER", 5, "Registrant holds many domains"))

    if rec["days_since_details_updated"] >= STALE_DAYS:
        out.append(Finding("STALE_DETAILS", 10, "Registrant details not updated for over a year"))

    return out
