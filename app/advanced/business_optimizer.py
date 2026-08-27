from __future__ import annotations

from dataclasses import dataclass, field

from .optimizer import optimizer


@dataclass
class KPIs:
    leads: int = 0
    contact_rate: float = 0.0      # answered / dialed
    qualification_rate: float = 0.0
    conversion_rate: float = 0.0   # booked-or-paid / qualified
    opt_out_rate: float = 0.0
    avg_sentiment: float = 0.0


# Diagnostic rules: (condition, lever, recommended action). The optimizer closes
# the loop by tuning provider/voice; these target funnel and policy levers.
RULES = [
    (lambda k: k.contact_rate < 0.35, "reachability",
     "Rotate caller-ID via number pools and shift dialing into higher-answer windows."),
    (lambda k: k.qualification_rate < 0.4, "discovery",
     "Strengthen discovery questions; qualify earlier before pitching."),
    (lambda k: k.conversion_rate < 0.25, "closing",
     "Route qualified leads to human closers and A/B the offer framing."),
    (lambda k: k.opt_out_rate > 0.08, "compliance",
     "Tighten targeting and frequency; review scripts for pushiness."),
    (lambda k: k.avg_sentiment < 0.0, "experience",
     "Slow pacing, add empathy acknowledgements, re-tune voice via the optimizer."),
]


@dataclass
class BusinessOptimizer:
    """Turns funnel metrics into ranked, actionable recommendations and triggers
    the model/voice optimizer — an always-on loop aiming the whole system at
    conversions rather than tuning one call at a time."""

    history: list[dict] = field(default_factory=list)

    def diagnose(self, kpis: KPIs) -> list[dict]:
        findings = []
        for cond, lever, action in RULES:
            try:
                if cond(kpis):
                    findings.append({"lever": lever, "action": action})
            except Exception:
                continue
        return findings

    def optimize(self, kpis: KPIs, auto_tune: bool = True) -> dict:
        findings = self.diagnose(kpis)
        tuning = optimizer.recommendation()
        if auto_tune and not any(b.get("best") for b in tuning.values()):
            tuning = optimizer.simulate(trials=150)
        # priority = number of failing gates, plus explicit weighting for compliance
        priority = len(findings) + (2 if any(f["lever"] == "compliance" for f in findings) else 0)
        result = {"kpis": kpis.__dict__, "findings": findings,
                  "recommended_config": tuning, "priority": priority,
                  "status": "healthy" if not findings else "action_required"}
        self.history.append(result)
        return result


business_optimizer = BusinessOptimizer()
