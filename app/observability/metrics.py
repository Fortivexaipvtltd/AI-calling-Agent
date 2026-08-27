from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    """Tiny dependency-free metrics store exposed at /metrics in Prometheus text
    format. Swap for prometheus_client if you need histograms/labels at scale."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._latencies: list[float] = []
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] += value

    def observe_latency(self, ms: float) -> None:
        with self._lock:
            self._latencies.append(ms)
            if len(self._latencies) > 5000:
                self._latencies = self._latencies[-5000:]

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self._latencies)
        def p(q):
            return lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0.0
        return {"requests": sum(v for (n, _), v in self._counters.items()
                                if n == "http_requests_total"),
                "p50_ms": round(p(0.50), 1), "p95_ms": round(p(0.95), 1),
                "p99_ms": round(p(0.99), 1)}

    def render(self) -> str:
        lines = ["# metrics (prometheus text v0.0.4)"]
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lbl = ("{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}") if labels else ""
                lines.append(f"{name}{lbl} {value}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"{name} {value}")
            lat = sorted(self._latencies)
        if lat:
            def q(x): return lat[min(len(lat) - 1, int(x * len(lat)))]
            lines += [f'http_request_latency_ms{{quantile="0.5"}} {q(0.5):.1f}',
                      f'http_request_latency_ms{{quantile="0.95"}} {q(0.95):.1f}',
                      f'http_request_latency_ms{{quantile="0.99"}} {q(0.99):.1f}']
        return "\n".join(lines) + "\n"


metrics = Metrics()
