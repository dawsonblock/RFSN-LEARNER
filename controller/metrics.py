# controller/metrics.py
"""
Prometheus-compatible metrics for RFSN agent.

Exposes counters, gauges, and histograms for:
- Tool execution counts and latencies
- Gate decisions (allow/deny)
- Replay cache hits/misses
- Error rates by type
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class Counter:
    """Thread-safe counter."""

    value: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def inc(self, amount: int = 1) -> None:
        with self._lock:
            self.value += amount

    def get(self) -> int:
        with self._lock:
            return self.value


@dataclass
class Gauge:
    """Thread-safe gauge (can go up or down)."""

    value: float = 0.0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def set(self, value: float) -> None:
        with self._lock:
            self.value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self.value -= amount

    def get(self) -> float:
        with self._lock:
            return self.value


@dataclass
class Histogram:
    """Simple histogram with predefined buckets."""

    buckets: tuple[float, ...] = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    _counts: dict[float, int] = field(default_factory=lambda: defaultdict(int))
    _sum: float = 0.0
    _count: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1

    def get(self) -> dict[str, Any]:
        with self._lock:
            result = {
                "sum": self._sum,
                "count": self._count,
                "buckets": {str(b): self._counts[b] for b in self.buckets},
            }
            if self._count > 0:
                result["mean"] = self._sum / self._count
            return result


class MetricsRegistry:
    """Registry for all metrics."""

    def __init__(self) -> None:
        self._lock = Lock()

        # Tool metrics
        self.tool_calls_total: dict[str, Counter] = defaultdict(Counter)
        self.tool_errors_total: dict[str, Counter] = defaultdict(Counter)
        self.tool_duration_seconds: dict[str, Histogram] = defaultdict(Histogram)

        # Gate metrics
        self.gate_decisions: dict[str, Counter] = defaultdict(Counter)

        # Replay metrics
        self.replay_hits = Counter()
        self.replay_misses = Counter()

        # Session metrics
        self.active_sessions = Gauge()
        self.total_messages = Counter()

        # Error metrics
        self.errors_by_type: dict[str, Counter] = defaultdict(Counter)

    def record_tool_call(
        self,
        tool_name: str,
        duration_seconds: float,
        success: bool = True,
    ) -> None:
        """Record a tool call with timing."""
        self.tool_calls_total[tool_name].inc()
        self.tool_duration_seconds[tool_name].observe(duration_seconds)
        if not success:
            self.tool_errors_total[tool_name].inc()

    def record_gate_decision(self, decision: str) -> None:
        """Record a gate decision (allow/deny)."""
        self.gate_decisions[decision].inc()

    def record_replay(self, hit: bool) -> None:
        """Record a replay cache hit or miss."""
        if hit:
            self.replay_hits.inc()
        else:
            self.replay_misses.inc()

    def record_error(self, error_type: str) -> None:
        """Record an error by type."""
        self.errors_by_type[error_type].inc()

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        # Tool calls
        lines.append("# HELP rfsn_tool_calls_total Total tool calls by name")
        lines.append("# TYPE rfsn_tool_calls_total counter")
        for name, counter in self.tool_calls_total.items():
            lines.append(f'rfsn_tool_calls_total{{tool="{name}"}} {counter.get()}')

        # Tool errors
        lines.append("# HELP rfsn_tool_errors_total Tool errors by name")
        lines.append("# TYPE rfsn_tool_errors_total counter")
        for name, counter in self.tool_errors_total.items():
            lines.append(f'rfsn_tool_errors_total{{tool="{name}"}} {counter.get()}')

        # Tool durations (histogram)
        lines.append("# HELP rfsn_tool_duration_seconds Tool execution duration")
        lines.append("# TYPE rfsn_tool_duration_seconds histogram")
        for name, hist in self.tool_duration_seconds.items():
            data = hist.get()
            for bucket, count in data.get("buckets", {}).items():
                lines.append(
                    f'rfsn_tool_duration_seconds_bucket{{tool="{name}",le="{bucket}"}} {count}'
                )
            lines.append(
                f'rfsn_tool_duration_seconds_sum{{tool="{name}"}} {data["sum"]}'
            )
            lines.append(
                f'rfsn_tool_duration_seconds_count{{tool="{name}"}} {data["count"]}'
            )

        # Gate decisions
        lines.append("# HELP rfsn_gate_decisions_total Gate decisions")
        lines.append("# TYPE rfsn_gate_decisions_total counter")
        for decision, counter in self.gate_decisions.items():
            lines.append(f'rfsn_gate_decisions_total{{decision="{decision}"}} {counter.get()}')

        # Replay metrics
        lines.append("# HELP rfsn_replay_hits_total Replay cache hits")
        lines.append("# TYPE rfsn_replay_hits_total counter")
        lines.append(f"rfsn_replay_hits_total {self.replay_hits.get()}")

        lines.append("# HELP rfsn_replay_misses_total Replay cache misses")
        lines.append("# TYPE rfsn_replay_misses_total counter")
        lines.append(f"rfsn_replay_misses_total {self.replay_misses.get()}")

        # Session metrics
        lines.append("# HELP rfsn_active_sessions Current active sessions")
        lines.append("# TYPE rfsn_active_sessions gauge")
        lines.append(f"rfsn_active_sessions {int(self.active_sessions.get())}")

        lines.append("# HELP rfsn_total_messages_total Total messages processed")
        lines.append("# TYPE rfsn_total_messages_total counter")
        lines.append(f"rfsn_total_messages_total {self.total_messages.get()}")

        # Errors
        lines.append("# HELP rfsn_errors_total Errors by type")
        lines.append("# TYPE rfsn_errors_total counter")
        for error_type, counter in self.errors_by_type.items():
            lines.append(f'rfsn_errors_total{{type="{error_type}"}} {counter.get()}')

        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as JSON-serializable dict."""
        return {
            "tool_calls": {k: v.get() for k, v in self.tool_calls_total.items()},
            "tool_errors": {k: v.get() for k, v in self.tool_errors_total.items()},
            "tool_durations": {k: v.get() for k, v in self.tool_duration_seconds.items()},
            "gate_decisions": {k: v.get() for k, v in self.gate_decisions.items()},
            "replay": {
                "hits": self.replay_hits.get(),
                "misses": self.replay_misses.get(),
            },
            "sessions": {
                "active": int(self.active_sessions.get()),
                "total_messages": self.total_messages.get(),
            },
            "errors": {k: v.get() for k, v in self.errors_by_type.items()},
        }


# Global metrics instance
METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Get global metrics registry."""
    return METRICS
