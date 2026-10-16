import threading
import time

import pytest

from cache import SingleFlight


def test_concurrent_calls_with_same_key_run_once_and_share_the_result():
    flight: SingleFlight[int] = SingleFlight()
    calls = []
    started = threading.Event()
    release = threading.Event()

    def slow():
        calls.append(1)
        started.set()
        release.wait(5)
        return 42

    results = []

    def worker():
        results.append(flight.do("k", slow))

    leader = threading.Thread(target=worker)
    leader.start()
    assert started.wait(5)
    followers = [threading.Thread(target=worker) for _ in range(5)]
    for thread in followers:
        thread.start()
    time.sleep(0.15)  # seguidores precisam estar esperando
    release.set()
    for thread in [leader, *followers]:
        thread.join(5)

    assert len(calls) == 1
    assert sorted(is_leader for _, is_leader in results) == [False] * 5 + [True]
    assert {value for value, _ in results} == {42}


def test_different_keys_do_not_block_each_other():
    flight: SingleFlight[str] = SingleFlight()
    gate = threading.Event()
    out = {}

    def blocked():
        out["a"] = flight.do("a", lambda: (gate.wait(5), "A")[1])

    thread = threading.Thread(target=blocked)
    thread.start()
    time.sleep(0.1)
    assert flight.do("b", lambda: "B") == ("B", True)  # nao espera pela chave "a"
    gate.set()
    thread.join(5)
    assert out["a"] == ("A", True)


def test_error_is_propagated_to_leader_and_followers_and_not_cached():
    flight: SingleFlight[int] = SingleFlight()
    started, release = threading.Event(), threading.Event()
    errors = []

    def failing():
        started.set()
        release.wait(5)
        raise ValueError("falhou")

    def worker():
        try:
            flight.do("k", failing)
        except ValueError as error:
            errors.append(str(error))

    threads = [threading.Thread(target=worker)]
    threads[0].start()
    assert started.wait(5)
    threads.append(threading.Thread(target=worker))
    threads[1].start()
    time.sleep(0.1)
    release.set()
    for thread in threads:
        thread.join(5)
    assert errors == ["falhou", "falhou"]
    assert flight.do("k", lambda: 7) == (7, True)  # a chave foi liberada


def test_sequential_calls_each_run():
    flight: SingleFlight[int] = SingleFlight()
    counter = iter(range(10))
    assert flight.do("k", lambda: next(counter)) == (0, True)
    assert flight.do("k", lambda: next(counter)) == (1, True)


def test_follower_times_out_when_leader_hangs():
    flight: SingleFlight[int] = SingleFlight(timeout=0.2)
    release = threading.Event()
    started = threading.Event()

    def hang():
        started.set()
        release.wait(5)
        return 1

    leader = threading.Thread(target=lambda: flight.do("k", hang))
    leader.start()
    assert started.wait(5)
    with pytest.raises(TimeoutError):
        flight.do("k", lambda: 2)
    release.set()
    leader.join(5)
