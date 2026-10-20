"""Relogio e formato de data unicos: o mesmo texto ISO em todos os armazens."""

from datetime import datetime, timedelta, timezone

import timeutil


def test_iso_keeps_the_timezone_and_cuts_at_seconds():
    moment = datetime(2026, 10, 20, 9, 5, 7, 123456, tzinfo=timezone.utc)
    assert timeutil.iso(moment) == "2026-10-20T09:05:07+00:00"


def test_iso_utc_converts_other_timezones_before_formatting():
    moment = datetime(2026, 10, 20, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert timeutil.iso_utc(moment) == "2026-10-20T12:00:00+00:00"
    assert timeutil.iso(moment) == "2026-10-20T09:00:00-03:00"


def test_utcnow_is_timezone_aware_and_the_iso_helper_matches_its_format():
    assert timeutil.utcnow().tzinfo == timezone.utc
    text = timeutil.utcnow_iso()
    assert len(text) == 25 and text.endswith("+00:00") and datetime.fromisoformat(text).tzinfo is not None
