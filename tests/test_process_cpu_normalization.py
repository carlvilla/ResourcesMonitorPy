"""Spec test: process CPU% values stored by the collector are never > 100%.

The project requires every process CPU% reaching the UI to be expressed as
"% of whole system" and capped at 100. The collector funnels every process
sample through one of two homogeneous builders — `sample_process_via_psutil`
(for processes psutil can read) or `sample_process_via_ps` (for SIP-blocked
processes like WindowServer). Both must satisfy the spec.

This test exercises both code paths with arbitrarily inflated raw CPU values
and asserts the contract holds.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from collector import (
    normalize_process_cpu,
    sample_process_via_ps,
    sample_process_via_psutil,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _fake_psutil_proc(cpu_raw: float):
    """Mimic the shape of `psutil.Process` returned by `process_iter`."""
    proc = SimpleNamespace(
        info={
            "pid": 1234,
            "name": "fakeproc",
            "cpu_percent": cpu_raw,
            "memory_info": SimpleNamespace(rss=50 * 1024 * 1024),  # 50 MB
            "status": "running",
            "num_threads": 4,
        }
    )
    proc.num_ctx_switches = lambda: SimpleNamespace(voluntary=10, involuntary=2)
    return proc


# Range covers: idle, partial, exactly one core, exceeding cores ×100,
# absurd outliers — caller can never push the result above 100.
_RAW_CPU_VALUES = [0, 1, 50, 99, 100, 200, 400, 800, 1600, 9_999, 99_999]


# ── psutil sampler path ───────────────────────────────────────────────────


@pytest.mark.parametrize("cpu_raw", _RAW_CPU_VALUES)
def test_psutil_sample_cpu_within_bounds(cpu_raw):
    sample = sample_process_via_psutil(_fake_psutil_proc(cpu_raw))
    assert sample is not None
    _, _, cpu, *_ = sample
    assert 0.0 <= cpu <= 100.0


def test_psutil_sample_returns_homogeneous_shape():
    sample = sample_process_via_psutil(_fake_psutil_proc(50.0))
    assert sample is not None
    pid, name, cpu, mem_mb, status, threads, vol_ctx, invol_ctx = sample
    assert isinstance(pid, int)
    assert isinstance(name, str)
    assert isinstance(cpu, float)
    assert isinstance(mem_mb, float)
    assert isinstance(status, str)
    assert isinstance(threads, int)
    assert isinstance(vol_ctx, int)
    assert isinstance(invol_ctx, int)


# ── ps (WindowServer) sampler path ────────────────────────────────────────


@pytest.mark.parametrize("cpu_raw", _RAW_CPU_VALUES)
def test_ps_sample_cpu_within_bounds(monkeypatch, cpu_raw):
    # Mock the underlying ps shellout to return a controlled raw CPU value.
    monkeypatch.setattr(
        "collector.read_process_via_ps",
        lambda pid: (cpu_raw, 250.0, 8),
    )
    sample = sample_process_via_ps(99, "WindowServer")
    assert sample is not None
    _, _, cpu, *_ = sample
    assert 0.0 <= cpu <= 100.0


def test_ps_sample_returns_none_when_ps_fails(monkeypatch):
    monkeypatch.setattr("collector.read_process_via_ps", lambda pid: None)
    assert sample_process_via_ps(99, "WindowServer") is None


# ── Pure helper (covers any caller, current or future) ───────────────────


@pytest.mark.parametrize(
    "cpu_raw, num_cores",
    [
        (raw, n)
        for n in (1, 2, 4, 8, 16, 32)
        for raw in (0, 100, 100 * n, 100 * n + 1, 99_999, -50)
    ],
)
def test_normalize_helper_within_bounds(cpu_raw, num_cores):
    result = normalize_process_cpu(cpu_raw, num_cores)
    assert 0.0 <= result <= 100.0
