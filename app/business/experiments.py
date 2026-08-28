from __future__ import annotations

import math
import random

from ..config import settings

# A/B testing over variants (scripts/prompts/voices). Assignment uses UCB1 so
# traffic automatically shifts toward winning variants — i.e. campaigns
# self-optimize based on real conversion outcomes, not guesswork.


def create(db, *, name: str, kind: str, variants: dict, org_id: str | None = None) -> dict:
    """variants = {variant_name: text_or_config}."""
    from ..models import Experiment
    v = {k: {"text": val, "trials": 0, "conversions": 0}
         for k, val in variants.items()}
    exp = Experiment(org_id=org_id or settings.default_org_id, name=name,
                     kind=kind, status="running", variants=v)
    db.add(exp)
    db.flush()
    return {"id": exp.id, "name": name, "kind": kind, "variants": list(variants)}


def _ucb_pick(variants: dict) -> str:
    total = sum(v["trials"] for v in variants.values())
    untried = [k for k, v in variants.items() if v["trials"] == 0]
    if untried:
        return random.choice(untried)
    t = max(1, total)

    def ucb(v: dict) -> float:
        mean = v["conversions"] / v["trials"] if v["trials"] else 0.0
        return mean + math.sqrt(2 * math.log(t) / v["trials"])
    return max(variants, key=lambda k: ucb(variants[k]))


def assign(db, experiment_id: str) -> dict:
    """Pick a variant to serve (records an exposure)."""
    import copy

    from ..models import Experiment
    exp = db.get(Experiment, experiment_id)
    if not exp or exp.status != "running":
        return {"ok": False, "error": "experiment_not_running"}
    variants = copy.deepcopy(exp.variants)
    choice = _ucb_pick(variants)
    variants[choice]["trials"] += 1
    exp.variants = variants
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(exp, "variants")
    db.flush()
    return {"ok": True, "experiment_id": experiment_id, "variant": choice,
            "text": variants[choice]["text"]}


def convert(db, experiment_id: str, variant: str) -> dict:
    """Record a conversion for a variant (the reward signal)."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    from ..models import Experiment
    exp = db.get(Experiment, experiment_id)
    if not exp:
        return {"ok": False, "error": "not_found"}
    variants = copy.deepcopy(exp.variants)
    if variant in variants:
        variants[variant]["conversions"] += 1
        exp.variants = variants
        flag_modified(exp, "variants")
        db.flush()
    return {"ok": True}


def results(db, experiment_id: str) -> dict:
    from ..models import Experiment
    exp = db.get(Experiment, experiment_id)
    if not exp:
        return {"ok": False, "error": "not_found"}
    rows = []
    for name, v in exp.variants.items():
        rate = v["conversions"] / v["trials"] if v["trials"] else 0.0
        rows.append({"variant": name, "trials": v["trials"],
                     "conversions": v["conversions"], "rate": round(rate, 3)})
    rows.sort(key=lambda r: r["rate"], reverse=True)
    leader = rows[0] if rows else None
    # Self-optimize: once a variant has a clear lead with enough data, promote it.
    optimized = False
    if leader and leader["trials"] >= 20 and leader["rate"] > 0:
        second = rows[1]["rate"] if len(rows) > 1 else 0.0
        if leader["rate"] >= second * 1.3:
            optimized = True
    return {"ok": True, "experiment_id": experiment_id, "name": exp.name,
            "kind": exp.kind, "results": rows, "leader": leader,
            "should_promote": optimized}
