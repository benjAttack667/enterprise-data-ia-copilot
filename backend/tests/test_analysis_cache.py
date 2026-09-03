"""Unit tests for the bounded in-memory analysis cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sys
from threading import Barrier, Event, Lock
import time

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.src.analysis_cache import AnalysisCache


def _wait_for_waiters(cache: AnalysisCache, expected: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with cache._lock:
            if any(flight.waiters >= expected for flight in cache._in_flight.values()):
                return
        time.sleep(0.005)
    raise AssertionError(f"{expected} waiter(s) ne se sont pas attachés au calcul.")


@pytest.mark.parametrize("max_entries", [0, -1, True, 1.5])
def test_cache_rejects_invalid_capacity(max_entries: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AnalysisCache(max_entries=max_entries)  # type: ignore[arg-type]


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5])
def test_cache_rejects_invalid_byte_budget(max_bytes: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AnalysisCache(max_bytes=max_bytes)  # type: ignore[arg-type]


def test_cache_computes_once_and_returns_defensive_copies() -> None:
    cache = AnalysisCache(max_entries=4, max_bytes=2_048)
    calls = 0
    source = {"summary": {"missing": [1, 2]}}

    def compute() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return source

    first = cache.get_or_compute("dataset-a", "quality", compute)
    source["summary"]["missing"].append(3)  # type: ignore[index,union-attr]
    first["summary"]["missing"].append(4)  # type: ignore[index,union-attr]
    second = cache.get_or_compute("dataset-a", "quality", compute)

    assert second == {"summary": {"missing": [1, 2]}}
    assert first is not second
    assert calls == 1
    metrics = cache.metrics()
    assert {
        key: metrics[key]
        for key in ("hits", "misses", "entries", "max_entries", "max_bytes")
    } == {
        "hits": 1,
        "misses": 1,
        "entries": 1,
        "max_entries": 4,
        "max_bytes": 2_048,
    }
    assert 0 < metrics["bytes"] <= metrics["max_bytes"]


def test_options_are_order_independent_and_type_preserving() -> None:
    cache = AnalysisCache(max_entries=4)
    calls = 0

    def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    first = cache.get_or_compute(
        "dataset-a",
        "dashboard",
        compute,
        options={"dimension": "country", "limit": 1},
    )
    reordered = cache.get_or_compute(
        "dataset-a",
        "dashboard",
        compute,
        options={"limit": 1, "dimension": "country"},
    )
    boolean_option = cache.get_or_compute(
        "dataset-a",
        "dashboard",
        compute,
        options={"dimension": "country", "limit": True},
    )

    assert (first, reordered, boolean_option) == (1, 1, 2)
    assert cache.metrics()["entries"] == 2


def test_lru_eviction_keeps_recently_read_entries() -> None:
    cache = AnalysisCache(max_entries=2)

    assert cache.get_or_compute("dataset-a", "quality", lambda: "quality") == "quality"
    assert cache.get_or_compute("dataset-a", "anomalies", lambda: "anomalies") == "anomalies"
    assert cache.get_or_compute("dataset-a", "quality", lambda: "unexpected") == "quality"
    assert cache.get_or_compute("dataset-a", "overview", lambda: "overview") == "overview"
    assert cache.get_or_compute("dataset-a", "anomalies", lambda: "recomputed") == "recomputed"

    metrics = cache.metrics()
    assert {
        key: metrics[key]
        for key in ("hits", "misses", "entries", "max_entries")
    } == {
        "hits": 1,
        "misses": 4,
        "entries": 2,
        "max_entries": 2,
    }
    assert 0 < metrics["bytes"] <= metrics["max_bytes"]


def test_lru_eviction_enforces_byte_budget_and_recency() -> None:
    value_size = sys.getsizeof("a" * 128)
    cache = AnalysisCache(max_entries=10, max_bytes=value_size * 2)

    assert cache.get_or_compute("dataset-a", "a", lambda: "a" * 128) == "a" * 128
    assert cache.get_or_compute("dataset-a", "b", lambda: "b" * 128) == "b" * 128
    # Refresh A: the byte-budget eviction caused by C must now remove B.
    assert cache.get_or_compute("dataset-a", "a", lambda: "wrong") == "a" * 128
    assert cache.get_or_compute("dataset-a", "c", lambda: "c" * 128) == "c" * 128
    assert cache.metrics()["bytes"] == value_size * 2

    assert cache.get_or_compute("dataset-a", "b", lambda: "d" * 128) == "d" * 128
    metrics = cache.metrics()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 4
    assert metrics["entries"] == 2
    assert metrics["bytes"] == value_size * 2
    assert metrics["max_bytes"] == value_size * 2


def test_value_larger_than_byte_budget_is_returned_but_never_cached() -> None:
    cache = AnalysisCache(max_entries=4, max_bytes=64)
    calls = 0

    def compute() -> str:
        nonlocal calls
        calls += 1
        return "x" * 256

    assert cache.get_or_compute("dataset-a", "overview", compute) == "x" * 256
    assert cache.get_or_compute("dataset-a", "overview", compute) == "x" * 256

    assert calls == 2
    assert cache.metrics() == {
        "hits": 0,
        "misses": 2,
        "entries": 0,
        "max_entries": 4,
        "bytes": 0,
        "max_bytes": 64,
    }


def test_byte_metrics_follow_dataset_invalidation_and_clear() -> None:
    first_value = "a" * 128
    second_value = "b" * 128
    value_size = sys.getsizeof(first_value)
    cache = AnalysisCache(max_entries=4, max_bytes=value_size * 3)

    cache.get_or_compute("dataset-a", "quality", lambda: first_value)
    cache.get_or_compute("dataset-b", "quality", lambda: second_value)
    assert cache.metrics() == {
        "hits": 0,
        "misses": 2,
        "entries": 2,
        "max_entries": 4,
        "bytes": value_size * 2,
        "max_bytes": value_size * 3,
    }

    assert cache.invalidate_dataset("dataset-a") == 1
    assert cache.metrics()["bytes"] == value_size
    assert cache.clear() == 1
    assert cache.metrics()["bytes"] == 0
    assert cache.metrics()["entries"] == 0


def test_dataset_keys_cannot_leak_results_and_can_be_pruned() -> None:
    cache = AnalysisCache(max_entries=8)

    assert cache.get_or_compute("old-id", "quality", lambda: "old") == "old"
    assert cache.get_or_compute("new-id", "quality", lambda: "new") == "new"
    assert cache.get_or_compute("new-id", "anomalies", lambda: "new-a") == "new-a"

    assert cache.retain_dataset("new-id") == 1
    assert cache.metrics()["entries"] == 2
    assert cache.get_or_compute("new-id", "quality", lambda: "wrong") == "new"
    assert cache.get_or_compute("old-id", "quality", lambda: "old-again") == "old-again"
    assert cache.invalidate_dataset("old-id") == 1


def test_concurrent_callers_share_one_computation() -> None:
    cache = AnalysisCache(max_entries=4)
    computation_started = Event()
    release_computation = Event()
    calls = 0
    calls_lock = Lock()

    def compute() -> dict[str, int]:
        nonlocal calls
        with calls_lock:
            calls += 1
        computation_started.set()
        assert release_computation.wait(timeout=5)
        return {"score": 98}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(cache.get_or_compute, "dataset-a", "quality", compute)
            for _ in range(8)
        ]
        assert computation_started.wait(timeout=5)
        release_computation.set()
        results = [future.result(timeout=5) for future in futures]

    assert results == [{"score": 98}] * 8
    assert calls == 1
    metrics = cache.metrics()
    assert {
        key: metrics[key]
        for key in ("hits", "misses", "entries", "max_entries")
    } == {
        "hits": 7,
        "misses": 1,
        "entries": 1,
        "max_entries": 4,
    }
    assert 0 < metrics["bytes"] <= metrics["max_bytes"]


def test_invalidation_during_computation_prevents_stale_reinsertion() -> None:
    cache = AnalysisCache(max_entries=4)
    computation_started = Event()
    release_computation = Event()

    def slow_compute() -> str:
        computation_started.set()
        assert release_computation.wait(timeout=5)
        return "stale"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            cache.get_or_compute, "dataset-a", "quality", slow_compute
        )
        assert computation_started.wait(timeout=5)
        assert cache.invalidate_dataset("dataset-a") == 0
        release_computation.set()
        assert future.result(timeout=5) == "stale"

    assert cache.metrics()["entries"] == 0
    assert cache.get_or_compute("dataset-a", "quality", lambda: "fresh") == "fresh"
    assert cache.metrics()["misses"] == 2


def test_waiter_started_before_invalidation_cannot_reinsert_stale_dataset() -> None:
    cache = AnalysisCache(max_entries=4)
    callers_ready = Barrier(3)
    computation_started = Event()
    release_first_computation = Event()
    calls = 0
    calls_lock = Lock()

    def compute() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            computation_started.set()
            assert release_first_computation.wait(timeout=5)
        return f"old-{call_number}"

    def invoke() -> str:
        callers_ready.wait(timeout=5)
        return cache.get_or_compute("dataset-a", "quality", compute)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        callers_ready.wait(timeout=5)
        assert computation_started.wait(timeout=5)
        _wait_for_waiters(cache, 1)
        cache.invalidate_dataset("dataset-a")
        release_first_computation.set()
        assert [future.result(timeout=5) for future in futures] == ["old-1", "old-1"]

    assert calls == 1
    assert cache.metrics()["entries"] == 0
    assert cache.get_or_compute("dataset-a", "quality", lambda: "fresh") == "fresh"
    assert cache.metrics()["entries"] == 1


def test_caller_started_after_invalidation_does_not_join_obsolete_flight() -> None:
    cache = AnalysisCache(max_entries=4)
    old_computation_started = Event()
    release_old_computation = Event()

    def compute_old() -> str:
        old_computation_started.set()
        assert release_old_computation.wait(timeout=5)
        return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        old_future = pool.submit(
            cache.get_or_compute, "dataset-a", "quality", compute_old
        )
        assert old_computation_started.wait(timeout=5)
        assert cache.invalidate_dataset("dataset-a") == 0

        fresh_future = pool.submit(
            cache.get_or_compute,
            "dataset-a",
            "quality",
            lambda: "fresh",
        )
        # A post-invalidation caller uses the new epoch and need not wait for the
        # obsolete owner to finish.
        assert fresh_future.result(timeout=5) == "fresh"
        assert cache.metrics()["entries"] == 1

        release_old_computation.set()
        assert old_future.result(timeout=5) == "stale"

    assert cache.get_or_compute("dataset-a", "quality", lambda: "wrong") == "fresh"
    metrics = cache.metrics()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 2
    assert metrics["entries"] == 1


def test_concurrent_waiters_observe_the_same_failed_computation() -> None:
    cache = AnalysisCache(max_entries=4)
    callers_ready = Barrier(5)
    release_computation = Event()
    calls = 0

    def fail_once() -> str:
        nonlocal calls
        calls += 1
        computation_started.set()
        assert release_computation.wait(timeout=5)
        raise RuntimeError(f"failed-{calls}")

    def invoke() -> str:
        callers_ready.wait(timeout=5)
        return cache.get_or_compute("dataset-a", "quality", fail_once)

    computation_started = Event()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(invoke) for _ in range(4)]
        callers_ready.wait(timeout=5)
        assert computation_started.wait(timeout=5)
        _wait_for_waiters(cache, 3)
        release_computation.set()
        errors = []
        for future in futures:
            with pytest.raises(RuntimeError) as raised:
                future.result(timeout=5)
            errors.append(str(raised.value))

    assert calls == 1
    assert errors == ["failed-1"] * 4
    assert cache.metrics()["entries"] == 0
    assert len(cache._in_flight) == 0


def test_api_routes_share_one_cached_analysis_bundle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_compute = main_module._compute_analysis_bundle
    calls = 0

    def tracked_compute(snapshot: object) -> tuple[dict, dict, dict]:
        nonlocal calls
        calls += 1
        return original_compute(snapshot)  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "_compute_analysis_bundle", tracked_compute)

    first_overview = client.get("/api/overview")
    quality = client.get("/api/data-quality")
    anomalies = client.get("/api/anomalies")
    second_overview = client.get("/api/overview")

    assert first_overview.status_code == 200, first_overview.text
    assert quality.status_code == 200, quality.text
    assert anomalies.status_code == 200, anomalies.text
    assert second_overview.status_code == 200, second_overview.text
    assert calls == 1
    cache_metrics = second_overview.json()["analysis_cache"]
    assert {
        key: cache_metrics[key]
        for key in (
            "hits",
            "misses",
            "entries",
            "max_entries",
            "max_bytes",
            "hit_rate",
            "scope",
        )
    } == {
        "hits": 3,
        "misses": 1,
        "entries": 1,
        "max_entries": client.app.state.settings.analysis_cache_max_entries,
        "max_bytes": client.app.state.settings.analysis_cache_max_bytes,
        "hit_rate": 75.0,
        "scope": "process",
    }
    assert 0 < cache_metrics["bytes"] <= cache_metrics["max_bytes"]


def test_successful_upload_prunes_previous_dataset_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_compute = main_module._compute_analysis_bundle
    computed_dataset_ids: list[str] = []

    def tracked_compute(snapshot: object) -> tuple[dict, dict, dict]:
        computed_dataset_ids.append(snapshot.id)  # type: ignore[attr-defined]
        return original_compute(snapshot)  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "_compute_analysis_bundle", tracked_compute)

    initial = client.get("/api/overview")
    assert initial.status_code == 200, initial.text
    initial_id = initial.json()["dataset"]["id"]
    assert client.app.state.analysis_cache.metrics()["entries"] == 1

    upload = client.post(
        "/api/upload",
        files={
            "file": (
                "replacement.csv",
                b"country,revenue\nFR,100\nDE,200\nES,150\n",
                "text/csv",
            )
        },
    )

    assert upload.status_code == 200, upload.text
    replacement_id = upload.json()["dataset_id"]
    assert replacement_id != initial_id
    assert client.app.state.analysis_cache.metrics()["entries"] == 0

    replacement = client.get("/api/overview")
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["dataset"]["id"] == replacement_id
    assert replacement.json()["dataset"]["rows"] == 3
    assert computed_dataset_ids == [initial_id, replacement_id]
    assert replacement.json()["analysis_cache"]["entries"] == 1
    assert replacement.json()["analysis_cache"]["misses"] == 2


def test_failed_computation_is_not_cached() -> None:
    cache = AnalysisCache(max_entries=2)

    def fail() -> str:
        raise RuntimeError("analysis failed")

    with pytest.raises(RuntimeError, match="analysis failed"):
        cache.get_or_compute("dataset-a", "quality", fail)

    assert cache.metrics()["entries"] == 0
    assert cache.get_or_compute("dataset-a", "quality", lambda: "recovered") == "recovered"


@pytest.mark.parametrize(
    ("dataset_id", "operation", "options", "error"),
    [
        ("", "quality", None, ValueError),
        ("dataset-a", "  ", None, ValueError),
        ("dataset-a", "quality", {"threshold": float("nan")}, ValueError),
        ("dataset-a", "quality", {"unsupported": object()}, TypeError),
        ("dataset-a", "quality", {1: "invalid"}, TypeError),
    ],
)
def test_invalid_keys_fail_fast(
    dataset_id: str,
    operation: str,
    options: dict[str, object] | None,
    error: type[Exception],
) -> None:
    cache = AnalysisCache()

    with pytest.raises(error):
        cache.get_or_compute(dataset_id, operation, lambda: "value", options=options)
