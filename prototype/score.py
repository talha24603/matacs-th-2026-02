"""Deterministic scoring: extracted facts + criteria config -> ranking.json.

No AI here. Same facts and same config always give the same output.

    python score.py criteria_solar_v1.json sample_extractions.json > ../ranking.json
"""
import json
import sys

OPS = {
    "==": lambda a, b: a == b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def linear(value, zero_at, full_at):
    """0-100, linear between the two anchors. Works for lower-is-better too."""
    frac = (value - zero_at) / (full_at - zero_at)
    return max(0.0, min(1.0, frac)) * 100


def money(v):
    return f"${v:,.0f}"


def evaluate(facts, config):
    val = lambda f: facts["fields"].get(f, {}).get("value")
    flags, failures = [], []

    # 1. Integrity: any instruction aimed at the reviewer/AI is flagged, never obeyed.
    for text in facts.get("embedded_instructions", []):
        flags.append(f"embedded instruction to reviewers ({text}); ignored for scoring")

    # 2. Mandatory pass/fail. Missing evidence is "unclear" -> human, not an automatic fail.
    for crit in config["mandatory"]:
        for chk in crit["checks"]:
            v = val(chk["field"])
            if v is None:
                flags.append(f"mandatory '{crit['label']}' not confirmed in proposal")
            elif not OPS[chk["op"]](v, chk["value"]):
                failures.append(crit["label"])

    # 3. Project hard limits.
    for lim in config["hard_limits"]:
        v = val(lim["field"])
        if v is None:
            flags.append(f"no value for {lim['field']}; cannot confirm '{lim['label']}'")
        elif not OPS[lim["op"]](v, lim["value"]):
            failures.append(f"breaks {lim['label']}")

    # 4. Weighted scoring from config formulas.
    breakdown = {}
    for c in config["weighted"]:
        if c["method"] == "linear":
            v = val(c["field"])
            pct = 0.0 if v is None else linear(v, c["zero_at"], c["full_at"])
            w = c.get("window")
            if w and val(w["field"]) is not None and val(w["field"]) < w["min"]:
                flags.append(f"{c['label'].lower()}: {w['note']}")
        elif c["method"] == "average":
            parts = [linear(val(p["field"]) or 0, p["zero_at"], p["full_at"]) for p in c["parts"]]
            pct = sum(parts) / len(parts)
        elif c["method"] == "checklist":
            # Not mentioned counts as not offered; this is a quality criterion, not a gate.
            pct = 100.0 * sum(1 for f in c["fields"] if val(f) is True) / len(c["fields"])
        else:
            raise ValueError(f"unknown method {c['method']}")
        breakdown[c["id"]] = round(pct * c["weight"] / 100, 1)

    total = round(sum(breakdown.values()), 1)
    return total, breakdown, flags, failures


def summary(facts, breakdown):
    val = lambda f: facts["fields"][f]["value"]
    weeks = val("completion_weeks")
    team = sum(1 for f in ("named_project_lead", "crew_identified", "safety_plan",
                           "performance_monitoring") if val(f) is True)
    return (f"experience {val('qualifying_projects')} installs ({breakdown['experience']}/30), "
            f"price {money(val('total_price_cad'))} ({breakdown['price']}/25), "
            f"{weeks if weeks is not None else '?'} wks ({breakdown['timeline']}/15), "
            f"warranty {val('panel_warranty_years')}y/{val('workmanship_warranty_years')}y "
            f"({breakdown['warranty']}/15), team {team}/4 ({breakdown['team']}/15)")


def main(config_path, facts_path):
    config = json.load(open(config_path, encoding="utf-8"))
    all_facts = {k: v for k, v in json.load(open(facts_path, encoding="utf-8")).items()
                 if not k.startswith("_")}

    rows = []
    for letter, facts in sorted(all_facts.items()):
        total, breakdown, flags, failures = evaluate(facts, config)
        if failures:
            rows.append({"proposal": letter, "rank": None, "status": "ineligible", "score": None,
                         "reason": "Fails: " + "; ".join(failures) + ". Not scored."})
        elif flags:
            rows.append({"proposal": letter, "rank": None, "status": "flagged", "score": None,
                         "reason": "Needs human review: " + "; ".join(flags)
                                   + f". Provisional {total} ({summary(facts, breakdown)})."})
        else:
            rows.append({"proposal": letter, "rank": None, "status": "ranked", "score": total,
                         "reason": summary(facts, breakdown)})

    ranked = sorted((r for r in rows if r["status"] == "ranked"), key=lambda r: -r["score"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["reason"] = f"{r['score']}/100: " + r["reason"]

    order = {"ranked": 0, "flagged": 1, "ineligible": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["rank"] or 0, r["proposal"]))
    json.dump(rows, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main(*sys.argv[1:3])
