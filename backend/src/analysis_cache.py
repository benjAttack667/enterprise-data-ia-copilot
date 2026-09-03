"""Bounded, in-memory cache for deterministic dataset analyses.

The cache deliberately stores no dataframe or payload on disk.  Keys include the
immutable dataset identifier, the analysis operation and its normalized options,
so a newly activated dataset can never receive a previous dataset's result.
"""

from __future__ import annotations

import math
import sys
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from threading import Event, RLock
from typing import Any, TypeVar


T = TypeVar("T")
_FrozenValue = tuple[Any, ...]
DEFAULT_MAX_CACHE_BYTES = 8 * 1024 * 1024


def _required_identifier(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} doit être une chaîne de caractères.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} ne peut pas être vide.")
    return normalized


def _freeze_option(value: object) -> _FrozenValue:
    """Convert supported option values to stable, type-preserving tuples."""

    if isinstance(value, Enum):
        return ("enum", value.__class__.__qualname__, _freeze_option(value.value))
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Les options numériques du cache doivent être finies.")
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, Mapping):
        items: list[tuple[str, _FrozenValue]] = []
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("Les clés d'options imbriquées doivent être des chaînes.")
            items.append((key, _freeze_option(nested_value)))
        return ("mapping", tuple(sorted(items)))
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return ("sequence", tuple(_freeze_option(item) for item in value))
    raise TypeError(
        "Option de cache non prise en charge. Utilisez uniquement des valeurs JSON."
    )


def _deep_size(value: object, seen: set[int] | None = None) -> int:
    """Estimate retained Python memory while handling shared/cyclic objects."""

    visited = seen if seen is not None else set()
    identifier = id(value)
    if identifier in visited:
        return 0
    visited.add(identifier)
    size = sys.getsizeof(value)
    if isinstance(value, Mapping):
        return size + sum(
            _deep_size(key, visited) + _deep_size(item, visited)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return size + sum(_deep_size(item, visited) for item in value)
    return size


@dataclass(frozen=True, slots=True)
class _CacheKey:
    dataset_id: str
    operation: str
    options: tuple[tuple[str, _FrozenValue], ...]


@dataclass(slots=True)
class _InFlight:
    """Coordinate one computation and allow reliable concurrent invalidation."""

    completed: Event
    cancelled: bool = False
    has_result: bool = False
    result: object | None = None
    error: BaseException | None = None
    waiters: int = 0


class AnalysisCache:
    """Thread-safe, byte-bounded LRU with defensive copies and single-flight.

    ``get_or_compute`` computes a missing key outside the lock. Concurrent callers
    for that exact key wait for the first computation instead of duplicating it.
    Every stored and returned value is deep-copied so callers cannot mutate the
    cached representation.
    """

    def __init__(
        self,
        max_entries: int = 32,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    ) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise TypeError("max_entries doit être un entier.")
        if max_entries < 1:
            raise ValueError("max_entries doit être supérieur ou égal à 1.")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes doit être un entier.")
        if max_bytes < 1:
            raise ValueError("max_bytes doit être supérieur ou égal à 1.")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._entries: OrderedDict[_CacheKey, object] = OrderedDict()
        self._entry_sizes: dict[_CacheKey, int] = {}
        self._total_bytes = 0
        self._in_flight: dict[tuple[_CacheKey, int], _InFlight] = {}
        self._invalidation_epoch = 0
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(
        dataset_id: str,
        operation: str,
        options: Mapping[str, object] | None,
    ) -> _CacheKey:
        normalized_options: tuple[tuple[str, _FrozenValue], ...] = ()
        if options:
            if any(not isinstance(key, str) for key in options):
                raise TypeError("Les clés d'options doivent être des chaînes.")
            normalized_options = tuple(
                sorted((key, _freeze_option(value)) for key, value in options.items())
            )
        return _CacheKey(
            dataset_id=_required_identifier(dataset_id, "dataset_id"),
            operation=_required_identifier(operation, "operation"),
            options=normalized_options,
        )

    def get_or_compute(
        self,
        dataset_id: str,
        operation: str,
        compute: Callable[[], T],
        *,
        options: Mapping[str, object] | None = None,
    ) -> T:
        """Return a defensive copy of a cached value or compute it exactly once."""

        if not callable(compute):
            raise TypeError("compute doit être appelable.")
        key = self._key(dataset_id, operation, options)
        with self._lock:
            call_epoch = self._invalidation_epoch
            if key in self._entries:
                stored = self._entries[key]
                self._entries.move_to_end(key)
                self._hits += 1
                cache_hit = True
                owns_computation = False
                flight = None
            else:
                cache_hit = False
                flight_key = (key, call_epoch)
                flight = self._in_flight.get(flight_key)
                if flight is None:
                    flight = _InFlight(completed=Event())
                    self._in_flight[flight_key] = flight
                    self._misses += 1
                    owns_computation = True
                else:
                    flight.waiters += 1
                    owns_computation = False

        # Cached objects are immutable from the cache's perspective, so the
        # potentially expensive defensive copy does not need to hold the lock.
        if cache_hit:
            return deepcopy(stored)  # type: ignore[return-value]

        assert flight is not None
        if not owns_computation:
            # Every waiter observes the owner's exact outcome. Invalidation can
            # prevent publication, but never makes a pre-existing waiter retry
            # and republish work for an obsolete snapshot.
            flight.completed.wait()
            if flight.error is not None:
                raise flight.error
            if not flight.has_result:
                raise RuntimeError("Calcul single-flight terminé sans résultat.")
            with self._lock:
                self._hits += 1
            return deepcopy(flight.result)  # type: ignore[return-value]

        try:
            computed = compute()
            # Make both copies before publishing anything.  If the value cannot be
            # copied, the cache remains unchanged and callers receive the error.
            stored_copy = deepcopy(computed)
            return_copy = deepcopy(stored_copy)
            stored_size = _deep_size(stored_copy)
        except BaseException as exc:
            with self._lock:
                flight.error = exc
                if self._in_flight.get(flight_key) is flight:
                    self._in_flight.pop(flight_key, None)
                flight.completed.set()
            raise

        with self._lock:
            flight.result = stored_copy
            flight.has_result = True
            if (
                not flight.cancelled
                and self._invalidation_epoch == call_epoch
                and stored_size <= self._max_bytes
            ):
                previous_size = self._entry_sizes.get(key, 0)
                self._entries[key] = stored_copy
                self._entry_sizes[key] = stored_size
                self._total_bytes += stored_size - previous_size
                self._entries.move_to_end(key)
                while (
                    len(self._entries) > self._max_entries
                    or self._total_bytes > self._max_bytes
                ):
                    evicted_key, _ = self._entries.popitem(last=False)
                    self._total_bytes -= self._entry_sizes.pop(evicted_key)
            if self._in_flight.get(flight_key) is flight:
                self._in_flight.pop(flight_key, None)
            flight.completed.set()
        return return_copy

    def invalidate_dataset(self, dataset_id: str) -> int:
        """Remove one dataset and prevent its in-flight work from being reinserted."""

        normalized_id = _required_identifier(dataset_id, "dataset_id")
        with self._lock:
            self._invalidation_epoch += 1
            keys = [key for key in self._entries if key.dataset_id == normalized_id]
            for key in keys:
                self._entries.pop(key, None)
                self._total_bytes -= self._entry_sizes.pop(key)
            for (key, _), flight in self._in_flight.items():
                if key.dataset_id == normalized_id:
                    flight.cancelled = True
            return len(keys)

    def retain_dataset(self, dataset_id: str) -> int:
        """Prune all other datasets, cancelling stale in-flight publications."""

        normalized_id = _required_identifier(dataset_id, "dataset_id")
        with self._lock:
            self._invalidation_epoch += 1
            keys = [key for key in self._entries if key.dataset_id != normalized_id]
            for key in keys:
                self._entries.pop(key, None)
                self._total_bytes -= self._entry_sizes.pop(key)
            for (key, _), flight in self._in_flight.items():
                if key.dataset_id != normalized_id:
                    flight.cancelled = True
            return len(keys)

    def clear(self, *, reset_metrics: bool = False) -> int:
        """Clear all cached values and cancel publication of running computations."""

        with self._lock:
            removed = len(self._entries)
            self._invalidation_epoch += 1
            self._entries.clear()
            self._entry_sizes.clear()
            self._total_bytes = 0
            for flight in self._in_flight.values():
                flight.cancelled = True
            if reset_metrics:
                self._hits = 0
                self._misses = 0
            return removed

    def metrics(self) -> dict[str, int]:
        """Expose non-sensitive operational metrics for the overview/API."""

        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "entries": len(self._entries),
                "max_entries": self._max_entries,
                "bytes": self._total_bytes,
                "max_bytes": self._max_bytes,
            }
