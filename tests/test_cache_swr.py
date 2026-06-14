"""Tests for the stale-while-revalidate cache layer added during perf work."""

from __future__ import annotations

import time

import pytest

from services.cache import TTLCache


@pytest.fixture()
def memory_cache():
    """A cache with no disk persistence so tests stay isolated and fast."""

    return TTLCache(namespace="swr-test", persist=False)


def test_swr_cold_builds_synchronously(memory_cache):
    calls = {"n": 0}

    def builder():
        calls["n"] += 1
        return "fresh"

    # Nothing cached yet → build runs inline and returns its value.
    result = memory_cache.get_or_set_swr("k", builder, fresh_seconds=10)
    assert result == "fresh"
    assert calls["n"] == 1


def test_swr_within_fresh_window_no_rebuild(memory_cache):
    calls = {"n": 0}

    def builder():
        calls["n"] += 1
        return calls["n"]

    first = memory_cache.get_or_set_swr("k", builder, fresh_seconds=10)
    second = memory_cache.get_or_set_swr("k", builder, fresh_seconds=10)
    # Still fresh → second call serves the cached value, builder runs once.
    assert first == 1
    assert second == 1
    assert calls["n"] == 1


def test_swr_stale_serves_old_then_refreshes(memory_cache):
    calls = {"n": 0}

    def builder():
        calls["n"] += 1
        return f"v{calls['n']}"

    # Fresh window of 0 makes the value immediately stale, but a long
    # ``max_age_seconds`` keeps the stale copy around to be served.
    first = memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert first == "v1"
    assert calls["n"] == 1

    # Next call is past the fresh window → returns stale "v1" immediately and
    # kicks off a background rebuild.
    stale = memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert stale == "v1"  # served stale, not the not-yet-built v2

    # Give the background thread a moment to land the refresh.
    deadline = time.time() + 2
    while calls["n"] < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert calls["n"] == 2  # background refresh ran exactly once


def test_swr_background_refresh_is_deduplicated(memory_cache):
    calls = {"n": 0}

    def builder():
        calls["n"] += 1
        time.sleep(0.3)  # hold the refresh open so overlaps would collide
        return calls["n"]

    # Cold build (synchronous).
    memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert calls["n"] == 1

    # Fire several stale reads in quick succession; only one background
    # refresh should be in flight thanks to the per-key guard.
    for _ in range(5):
        memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)

    deadline = time.time() + 3
    while calls["n"] < 2 and time.time() < deadline:
        time.sleep(0.02)
    # One cold build + exactly one coalesced background refresh.
    assert calls["n"] == 2


def test_swr_builder_failure_keeps_serving_stale(memory_cache):
    state = {"n": 0}

    def builder():
        state["n"] += 1
        if state["n"] == 1:
            return "good"
        raise RuntimeError("upstream down")

    first = memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert first == "good"

    # Stale read triggers a background refresh that raises — the old value
    # must still be served and remain available for the next call.
    stale = memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert stale == "good"

    deadline = time.time() + 2
    while state["n"] < 2 and time.time() < deadline:
        time.sleep(0.02)

    # Even after the failed refresh, the good value is still cached.
    again = memory_cache.get_or_set_swr("k", builder, fresh_seconds=0, max_age_seconds=60)
    assert again == "good"
