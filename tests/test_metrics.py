# tests/test_metrics.py
"""Tests for Prometheus metrics module."""

from __future__ import annotations

import pytest

from controller.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics,
)


class TestCounter:
    """Test Counter metric."""

    def test_initial_value(self) -> None:
        c = Counter()
        assert c.get() == 0

    def test_increment(self) -> None:
        c = Counter()
        c.inc()
        assert c.get() == 1

    def test_increment_by_amount(self) -> None:
        c = Counter()
        c.inc(5)
        assert c.get() == 5


class TestGauge:
    """Test Gauge metric."""

    def test_initial_value(self) -> None:
        g = Gauge()
        assert g.get() == 0.0

    def test_set(self) -> None:
        g = Gauge()
        g.set(42.5)
        assert g.get() == 42.5

    def test_inc_dec(self) -> None:
        g = Gauge()
        g.inc(10)
        g.dec(3)
        assert g.get() == 7.0


class TestHistogram:
    """Test Histogram metric."""

    def test_observe(self) -> None:
        h = Histogram()
        h.observe(0.05)
        h.observe(0.5)
        h.observe(2.0)
        data = h.get()
        assert data["count"] == 3
        assert data["sum"] == 2.55

    def test_buckets(self) -> None:
        h = Histogram()
        h.observe(0.02)  # fits in 0.05 and higher
        data = h.get()
        assert data["buckets"]["0.05"] == 1
        assert data["buckets"]["1.0"] == 1

    def test_mean(self) -> None:
        h = Histogram()
        h.observe(0.1)
        h.observe(0.3)
        data = h.get()
        assert data["mean"] == pytest.approx(0.2)


class TestMetricsRegistry:
    """Test MetricsRegistry."""

    def test_record_tool_call(self) -> None:
        registry = MetricsRegistry()
        registry.record_tool_call("test_tool", 0.5, success=True)
        assert registry.tool_calls_total["test_tool"].get() == 1

    def test_record_tool_error(self) -> None:
        registry = MetricsRegistry()
        registry.record_tool_call("test_tool", 0.5, success=False)
        assert registry.tool_errors_total["test_tool"].get() == 1

    def test_record_gate_decision(self) -> None:
        registry = MetricsRegistry()
        registry.record_gate_decision("allow")
        registry.record_gate_decision("allow")
        registry.record_gate_decision("deny")
        assert registry.gate_decisions["allow"].get() == 2
        assert registry.gate_decisions["deny"].get() == 1

    def test_record_replay(self) -> None:
        registry = MetricsRegistry()
        registry.record_replay(hit=True)
        registry.record_replay(hit=False)
        registry.record_replay(hit=True)
        assert registry.replay_hits.get() == 2
        assert registry.replay_misses.get() == 1

    def test_to_prometheus(self) -> None:
        registry = MetricsRegistry()
        registry.record_tool_call("cat", 0.1)
        registry.record_gate_decision("allow")
        output = registry.to_prometheus()
        assert "rfsn_tool_calls_total" in output
        assert "rfsn_gate_decisions_total" in output
        assert 'tool="cat"' in output

    def test_to_dict(self) -> None:
        registry = MetricsRegistry()
        registry.record_tool_call("ls", 0.05)
        registry.active_sessions.set(3)
        data = registry.to_dict()
        assert "tool_calls" in data
        assert data["sessions"]["active"] == 3


class TestGlobalMetrics:
    """Test global metrics instance."""

    def test_get_metrics_returns_same_instance(self) -> None:
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2
