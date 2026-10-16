import pytest

from cache import TTLCache


class FakeClock:
    now = 0.0

    def __call__(self):
        return self.now


def test_get_missing_returns_none():
    assert TTLCache[str]().get("x") is None


def test_lru_evicts_least_recently_used():
    cache = TTLCache[int](max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # "a" passa a ser o mais recente
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1 and cache.get("c") == 3


def test_entries_expire_after_ttl():
    clock = FakeClock()
    cache = TTLCache[str](ttl=10, clock=clock)
    cache.set("k", "v")
    clock.now = 9.9
    assert cache.get("k") == "v"
    clock.now = 10.0
    assert cache.get("k") is None
    assert len(cache) == 0


def test_overwrite_refreshes_ttl_and_keeps_size():
    clock = FakeClock()
    cache = TTLCache[str](ttl=10, clock=clock)
    cache.set("k", "old")
    clock.now = 8
    cache.set("k", "new")
    clock.now = 15
    assert cache.get("k") == "new"
    assert len(cache) == 1


def test_invalid_configuration():
    with pytest.raises(ValueError):
        TTLCache(max_size=0)
    with pytest.raises(ValueError):
        TTLCache(ttl=0)
