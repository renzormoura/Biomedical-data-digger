import pytest

from ratelimit import RateLimitExceeded, SlidingWindowLimiter, client_key


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_allows_up_to_limit_then_blocks():
    limiter = SlidingWindowLimiter(limit=3, window=60, clock=FakeClock())
    for _ in range(3):
        limiter.check("a")
    with pytest.raises(RateLimitExceeded) as info:
        limiter.check("a")
    assert 0 < info.value.retry_after <= 60


def test_keys_are_independent():
    limiter = SlidingWindowLimiter(limit=1, window=60, clock=FakeClock())
    limiter.check("a")
    limiter.check("b")


def test_window_slides_and_frees_capacity():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=2, window=60, clock=clock)
    limiter.check("a")
    clock.now += 30
    limiter.check("a")
    clock.now += 31  # primeiro evento saiu da janela
    limiter.check("a")
    with pytest.raises(RateLimitExceeded):
        limiter.check("a")


def test_rejected_attempts_are_not_recorded():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window=10, clock=clock)
    limiter.check("a")
    for _ in range(5):
        with pytest.raises(RateLimitExceeded):
            limiter.check("a")
    clock.now += 10
    limiter.check("a")  # tentativas barradas nao geram "divida"


def test_stale_keys_are_evicted():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window=10, clock=clock, max_keys=5)
    for index in range(5):
        limiter.check(f"k{index}")
    clock.now += 11
    limiter.check("new")
    limiter.check("another")
    assert len(limiter._events) <= 3


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=0)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=1, window=0)


def test_client_key_uses_last_trusted_hop_not_spoofable_first_entry():
    headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}  # 6.6.6.6 forjado pelo cliente
    assert client_key(headers, "10.0.0.1", trusted_hops=1) == "203.0.113.9"


def test_client_key_falls_back_to_peer():
    assert client_key({}, "198.51.100.4") == "198.51.100.4"
    assert client_key(None, None) == "unknown"
    assert client_key({"x-forwarded-for": "1.1.1.1"}, "9.9.9.9", trusted_hops=0) == "9.9.9.9"
