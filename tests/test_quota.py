import pytest

from quota import QuotaExceeded, QuotaManager

DAY = 86400


class Clock:
    now = 10 * DAY + 100.0

    def __call__(self):
        return self.now


def test_charges_accumulate_until_budget_is_reached():
    quota = QuotaManager(guest_budget=1000, user_budget=5000, clock=Clock())
    quota.check("ip:1.1.1.1")
    quota.charge("ip:1.1.1.1", 600)
    assert quota.remaining("ip:1.1.1.1") == 400
    quota.check("ip:1.1.1.1")  # ainda abaixo
    quota.charge("ip:1.1.1.1", 600)  # pode estourar a ultima chamada, mas a proxima e barrada
    assert quota.remaining("ip:1.1.1.1") == 0
    with pytest.raises(QuotaExceeded) as info:
        quota.check("ip:1.1.1.1")
    assert info.value.budget == 1000 and "1.000" in str(info.value) and "00:00 UTC" in str(info.value)


def test_users_have_a_larger_budget_than_guests_and_identities_are_independent():
    quota = QuotaManager(guest_budget=100, user_budget=900, clock=Clock())
    assert quota.budget_for("ip:1.1.1.1") == 100 and quota.budget_for("u:ana@x.com") == 900
    quota.charge("ip:1.1.1.1", 100)
    with pytest.raises(QuotaExceeded):
        quota.check("ip:1.1.1.1")
    quota.check("ip:2.2.2.2")
    quota.check("u:ana@x.com")


def test_quota_resets_on_the_next_utc_day():
    clock = Clock()
    quota = QuotaManager(guest_budget=100, user_budget=100, clock=clock)
    quota.charge("ip:1.1.1.1", 100)
    with pytest.raises(QuotaExceeded):
        quota.check("ip:1.1.1.1")
    clock.now = 11 * DAY + 1
    quota.check("ip:1.1.1.1")
    assert quota.remaining("ip:1.1.1.1") == 100


def test_zero_budget_means_unlimited():
    quota = QuotaManager(guest_budget=0, user_budget=0, clock=Clock())
    quota.charge("ip:1.1.1.1", 10**9)
    quota.check("ip:1.1.1.1")
    assert quota.remaining("ip:1.1.1.1") is None


def test_non_positive_charges_are_ignored_and_negative_budgets_rejected():
    quota = QuotaManager(guest_budget=100, user_budget=100, clock=Clock())
    quota.charge("ip:1.1.1.1", 0)
    quota.charge("ip:1.1.1.1", -50)
    assert quota.remaining("ip:1.1.1.1") == 100
    with pytest.raises(ValueError):
        QuotaManager(guest_budget=-1, user_budget=0)


def test_old_days_are_purged_when_the_table_grows():
    clock = Clock()
    quota = QuotaManager(guest_budget=100, user_budget=100, clock=clock)
    for index in range(10_001):
        quota.charge(f"ip:{index}", 1)
    clock.now += DAY
    quota.charge("ip:novo", 1)
    assert len(quota._used) < 10_001
