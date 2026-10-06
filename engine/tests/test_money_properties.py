"""Property tests: invariants that must hold for every amount, not just examples."""

from hypothesis import given
from hypothesis import strategies as st

from nextpay_engine.money import Money

# Far beyond any real paycheck, in both directions.
cents = st.integers(min_value=-(10**15), max_value=10**15)
moneys = st.builds(Money, cents)
non_negative_moneys = st.builds(Money, st.integers(min_value=0, max_value=10**15))
parts = st.integers(min_value=1, max_value=500)


@given(non_negative_moneys, parts)
def test_split_conserves_every_cent(money: Money, n: int) -> None:
    result = money.split(n)
    assert len(result) == n
    assert sum(result, Money.zero()) == money


@given(non_negative_moneys, parts)
def test_split_parts_are_equal_except_last_takes_leftover(money: Money, n: int) -> None:
    result = money.split(n)
    share, *_ = result
    *leading, last = result
    assert all(part == share for part in leading)
    assert all(not part.is_negative() for part in (*leading, last))
    assert Money.zero() <= last - share < Money(n)


@given(moneys, moneys)
def test_add_then_subtract_round_trips(a: Money, b: Money) -> None:
    assert (a + b) - b == a


@given(moneys, moneys)
def test_add_is_commutative(a: Money, b: Money) -> None:
    assert a + b == b + a


@given(moneys, moneys, moneys)
def test_add_is_associative(a: Money, b: Money, c: Money) -> None:
    assert (a + b) + c == a + (b + c)


@given(moneys, moneys, st.integers(min_value=-1000, max_value=1000))
def test_multiply_distributes_over_add(a: Money, b: Money, k: int) -> None:
    assert (a + b) * k == a * k + b * k


@given(moneys)
def test_negation_is_additive_inverse(a: Money) -> None:
    assert a + (-a) == Money.zero()


@given(moneys, moneys)
def test_ordering_matches_cents(a: Money, b: Money) -> None:
    assert (a < b) == (a.cents < b.cents)
    assert (a == b) == (a.cents == b.cents)


@given(moneys)
def test_parse_round_trips_plain_decimal(money: Money) -> None:
    sign = "-" if money.cents < 0 else ""
    dollars, rem = divmod(abs(money.cents), 100)
    assert Money.parse(f"{sign}{dollars}.{rem:02d}") == money


@given(moneys)
def test_str_round_trips_after_removing_symbols(money: Money) -> None:
    assert Money.parse(str(money).replace("$", "").replace(",", "")) == money
