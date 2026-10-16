import pytest

from sessions import SessionSigner


class Clock:
    now = 1_000_000.0

    def __call__(self):
        return self.now


SECRET = "s" * 40


def test_roundtrip_and_unicode_user():
    signer = SessionSigner(SECRET)
    assert signer.verify(signer.issue("ana@exemplo.com")) == "ana@exemplo.com"
    assert signer.verify(signer.issue("joão@exemplo.com")) == "joão@exemplo.com"


def test_expired_token_is_rejected():
    clock = Clock()
    signer = SessionSigner(SECRET, ttl=60, clock=clock)
    token = signer.issue("a@b.com")
    clock.now += 61
    assert signer.verify(token) is None


def test_tampering_with_user_or_expiry_is_detected():
    signer = SessionSigner(SECRET)
    user, exp, sig = signer.issue("a@b.com").split(".")
    forged_user = SessionSigner(SECRET).issue("admin@b.com").split(".")[0]
    assert signer.verify(f"{forged_user}.{exp}.{sig}") is None
    assert signer.verify(f"{user}.{int(exp) + 10_000}.{sig}") is None


def test_token_from_other_secret_is_rejected():
    assert SessionSigner("o" * 40).verify(SessionSigner(SECRET).issue("a@b.com")) is None


@pytest.mark.parametrize("junk", [None, "", "abc", "a.b", "a.b.c.d", "!!!.123.sig", "...", "a." + "9" * 30 + ".b"])
def test_malformed_tokens_never_raise(junk):
    assert SessionSigner(SECRET).verify(junk) is None


def test_short_secret_is_rejected():
    with pytest.raises(ValueError):
        SessionSigner("curto")


def test_generated_secrets_are_long_and_unique():
    assert len(SessionSigner.generate_secret()) >= 48
    assert SessionSigner.generate_secret() != SessionSigner.generate_secret()
