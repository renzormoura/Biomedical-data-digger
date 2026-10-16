import json

import pytest
from loguru import logger

from usage import UsageLog, UsageRecord, client_kind, estimate_messages_tokens, estimate_tokens


def record(key="geral/sumario", prompt=1000, completion=400, cached=False, estimated=False, kind="guest"):
    return UsageRecord(key=key, model="m", prompt_tokens=prompt, completion_tokens=completion,
                       cached=cached, estimated=estimated, latency_ms=250, client_kind=kind)


def test_snapshot_aggregates_per_key_and_totals():
    log = UsageLog(clock=lambda: 1_700_000_000)
    log.record(record(prompt=1000, completion=500))
    log.record(record(prompt=1200, completion=300))
    log.record(record(cached=True, prompt=0, completion=0))
    log.record(record(key="medicina/pico", prompt=2000, completion=1000))
    snap = log.snapshot()
    sumario = snap["by_key"]["geral/sumario"]
    assert sumario["calls"] == 3 and sumario["cache_hits"] == 1 and sumario["cache_hit_rate"] == 0.333
    assert sumario["prompt_tokens"] == 2200 and sumario["completion_tokens"] == 800
    assert sumario["avg_total_tokens"] == 1500  # cache hit nao entra na media paga
    assert snap["totals"] == {"calls": 4, "cache_hits": 1, "prompt_tokens": 4200, "completion_tokens": 1800,
                              "total_tokens": 6000}
    assert snap["since"] == 1_700_000_000


def test_p95_and_estimated_counters():
    log = UsageLog()
    for total in range(1, 101):
        log.record(record(prompt=total, completion=0, estimated=total % 2 == 0))
    stats = log.snapshot()["by_key"]["geral/sumario"]
    assert stats["p95_total_tokens"] == 95 and stats["estimated_calls"] == 50


def test_samples_are_bounded():
    log = UsageLog()
    for _ in range(2000):
        log.record(record())
    assert len(log._stats["geral/sumario"].samples) == 500


def test_each_record_emits_one_structured_log_line_without_content():
    lines = []
    sink = logger.add(lambda message: lines.append(message.record["message"]), level="INFO")
    try:
        UsageLog().record(record(kind="user"))
    finally:
        logger.remove(sink)
    assert len(lines) == 1 and lines[0].startswith("llm_usage ")
    payload = json.loads(lines[0].split(" ", 1)[1])
    assert payload["client_kind"] == "user" and payload["prompt_tokens"] == 1000
    assert set(payload) == {"key", "model", "prompt_tokens", "completion_tokens", "cached", "estimated",
                            "latency_ms", "client_kind"}


def test_estimates_are_conservative_and_handle_empty():
    assert estimate_tokens("") == 0 and estimate_tokens("a" * 36) == 10
    assert estimate_messages_tokens([{"role": "user", "content": "a" * 72}, {"role": "system"}]) == 20


@pytest.mark.parametrize("client,kind", [("u:ana@x.com", "user"), ("ip:1.2.3.4", "guest"), ("local", "guest")])
def test_client_kind(client, kind):
    assert client_kind(client) == kind
