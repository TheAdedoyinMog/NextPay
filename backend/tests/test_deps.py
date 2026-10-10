"""The production defaults behind the dependencies that tests override."""

from datetime import UTC, datetime, timedelta

from app.api.deps import get_clock, get_password_hasher
from app.core.clock import utc_now


def test_the_clock_is_real_utc_time() -> None:
    assert get_clock() is utc_now
    now = utc_now()
    assert now.tzinfo is UTC
    assert abs(now - datetime.now(UTC)) < timedelta(seconds=5)


def test_production_hashes_with_full_strength_argon2id() -> None:
    hasher = get_password_hasher()
    assert get_password_hasher() is hasher  # one hasher, built once
    # RFC 9106 low-memory profile: 64 MiB, 3 passes, 4 lanes. Tests use far less.
    assert "$argon2id$v=19$m=65536,t=3,p=4$" in hasher.hash("correct horse battery")
