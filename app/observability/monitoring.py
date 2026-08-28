from __future__ import annotations

import json
import urllib.request
from collections import deque

from ..config import settings

# Lightweight in-process monitoring: rolling counters + threshold alerts. In a
# multi-instance deploy these would ship to Prometheus/Datadog; here they power
# the console health view and fire a webhook (e.g. Slack) on breach.


class Monitor:
    def __init__(self, window: int = 200) -> None:
        self.calls = 0
        self.failures = 0
        self.latencies: deque[float] = deque(maxlen=window)
        self.costs: deque[float] = deque(maxlen=window)
        self.alerts: list[dict] = []

    def record_call(self, *, ok: bool, latency_ms: float = 0.0, cost_usd: float = 0.0) -> None:
        self.calls += 1
        if not ok:
            self.failures += 1
        if latency_ms:
            self.latencies.append(latency_ms)
        if cost_usd:
            self.costs.append(cost_usd)
        self._check(latency_ms, cost_usd, ok)

    def _check(self, latency_ms: float, cost_usd: float, ok: bool) -> None:
        if latency_ms and latency_ms > settings.alert_latency_ms:
            self._alert("high_latency", f"latency {latency_ms:.0f}ms exceeds "
                        f"{settings.alert_latency_ms}ms")
        if cost_usd and cost_usd > settings.alert_cost_per_call_usd:
            self._alert("high_cost", f"call cost ${cost_usd:.2f} exceeds "
                        f"${settings.alert_cost_per_call_usd}")
        fail_rate = self.failures / self.calls if self.calls else 0
        if self.calls >= 10 and fail_rate > 0.3:
            self._alert("high_failure_rate", f"failure rate {fail_rate:.0%}")

    def _alert(self, kind: str, message: str) -> None:
        alert = {"kind": kind, "message": message}
        self.alerts.append(alert)
        self.alerts = self.alerts[-50:]
        if settings.alert_webhook_url:
            try:
                req = urllib.request.Request(
                    settings.alert_webhook_url,
                    data=json.dumps({"text": f"[Highh alert] {kind}: {message}"}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass

    def snapshot(self) -> dict:
        lat = sorted(self.latencies)
        p95 = lat[int(len(lat) * 0.95)] if lat else 0.0
        return {
            "calls": self.calls, "failures": self.failures,
            "failure_rate": round(self.failures / self.calls, 3) if self.calls else 0.0,
            "latency_ms_avg": round(sum(self.latencies) / len(self.latencies), 1)
            if self.latencies else 0.0,
            "latency_ms_p95": round(p95, 1),
            "avg_cost_usd": round(sum(self.costs) / len(self.costs), 4)
            if self.costs else 0.0,
            "recent_alerts": self.alerts[-10:],
        }


monitor = Monitor()
