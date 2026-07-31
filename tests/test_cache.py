"""cache.py — the behaviour app.py's caching relies on."""

import threading
import time

import pytest

from cache import DEFAULT_TTL_SECONDS, TTLCache, build_cache, cache_key


def test_hit_and_miss_counters():
    c = TTLCache(ttl=60)
    assert c.get("absent") is None
    c.set("k", {"v": 1})
    assert c.get("k") == {"v": 1}
    assert (c.hits, c.misses) == (1, 1)


def test_entries_expire():
    c = TTLCache(ttl=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(0.08)
    assert c.get("k") is None, "entry should have expired"
    assert len(c) == 0, "expired entry should be dropped, not left to accumulate"


def test_lru_eviction_keeps_the_recently_used():
    c = TTLCache(ttl=60, max_entries=3)
    for k in "abc":
        c.set(k, k)
    c.get("a")           # 'a' becomes most-recently-used, so 'b' is next out
    c.set("d", "d")
    assert len(c) == 3
    assert c.get("b") is None
    assert c.get("a") == "a"
    assert c.get("d") == "d"


def test_writing_the_same_key_does_not_grow_the_cache():
    c = TTLCache(ttl=60)
    for _ in range(10):
        c.set("k", "v")
    assert len(c) == 1


def test_clear_resets_entries_and_counters():
    c = TTLCache(ttl=60)
    c.set("k", "v")
    c.get("k")
    c.get("absent")
    c.clear()
    assert len(c) == 0 and c.hits == 0 and c.misses == 0


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------
def test_key_is_stable_across_dict_ordering():
    """The frontend doesn't guarantee JSON key order; the same polygon must
    still land on one entry."""
    a = cache_key("stats", 2024, {"type": "Polygon", "coordinates": [[[0, 0]]]})
    b = cache_key("stats", 2024, {"coordinates": [[[0, 0]]], "type": "Polygon"})
    assert a == b


def test_key_distinguishes_meaningful_differences():
    base = ("stats", 2024, {"type": "Polygon", "coordinates": [[[0, 0]]]})
    assert cache_key(*base) != cache_key("stats", 2019, base[2])
    assert cache_key(*base) != cache_key("tile", 2024, base[2])
    assert cache_key(*base) != cache_key("stats", 2024, {"type": "Polygon",
                                                        "coordinates": [[[0, 1]]]})


def test_key_distinguishes_none_from_missing():
    """A tile request with month=None and one with month=6 are different."""
    assert cache_key("tile", "ndvi", 2024, None) != cache_key("tile", "ndvi", 2024, 6)


def test_key_survives_a_restart():
    """sha256, not hash() — a salted hash would reshuffle keys per process."""
    assert cache_key("stats", 2024, {"a": 1}) == "99ab26b08c864d7e865815869ebd13dff8718044c46f18b35241ffdf1b0efe16"
    assert len(cache_key("x")) == 64


# ---------------------------------------------------------------------------
# Disabling
# ---------------------------------------------------------------------------
def test_ttl_zero_disables_caching():
    c = TTLCache(ttl=0)
    assert not c.enabled
    c.set("k", "v")
    assert c.get("k") is None
    assert len(c) == 0


def test_env_var_controls_ttl(monkeypatch):
    monkeypatch.setenv("CONTOUR_CACHE_TTL", "0")
    assert not build_cache().enabled

    monkeypatch.setenv("CONTOUR_CACHE_TTL", "42")
    assert build_cache().ttl == 42


def test_bad_env_var_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("CONTOUR_CACHE_TTL", "not-a-number")
    assert build_cache().ttl == DEFAULT_TTL_SECONDS


# ---------------------------------------------------------------------------
# Concurrency — FastAPI runs sync endpoints in a threadpool
# ---------------------------------------------------------------------------
def test_concurrent_access_does_not_corrupt_the_cache():
    c = TTLCache(ttl=60, max_entries=50)
    errors = []

    def worker(n):
        try:
            for i in range(200):
                c.set(f"k{i % 60}", n)
                c.get(f"k{i % 60}")
        except Exception as e:      # a race on the OrderedDict would land here
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(c) <= 50, "max_entries must hold under concurrent writes"
