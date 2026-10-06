from decimal import Decimal

import pytest

from nextpay_engine.money import Money

# --- Construction -----------------------------------------------------------


def test_stores_cents() -> None:
    assert Money(1234).cents == 1234


def test_allows_negative_and_zero() -> None:
    assert Money(-500).cents == -500
    assert Money(0).cents == 0


@pytest.mark.parametrize("bad", [12.34, 1.0, Decimal("12.34"), True, False, "1234", None])
def test_rejects_non_int_cents(bad: object) -> None:
    with pytest.raises(TypeError):
        Money(bad)  # type: ignore[arg-type]


def test_is_immutable() -> None:
    money = Money(100)
    with pytest.raises(AttributeError):
        money.cents = 200  # type: ignore[misc]


def test_equal_values_hash_equally() -> None:
    assert Money(100) == Money(100)
    assert hash(Money(100)) == hash(Money(100))
    assert len({Money(100), Money(100), Money(200)}) == 2


def test_zero() -> None:
    assert Money.zero() == Money(0)


# --- Parsing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("12.34", 1234),
        ("12.3", 1230),
        ("12", 1200),
        ("0", 0),
        ("0.01", 1),
        ("-0.50", -50),
        ("-12.34", -1234),
        ("-0", 0),
        ("007.05", 705),
        ("1000000.00", 100_000_000),
    ],
)
def test_parse_valid(text: str, cents: int) -> None:
    assert Money.parse(text) == Money(cents)


@pytest.mark.parametrize(
    "text",
    [
        "12.345",  # more than two decimal places: rejected, never rounded
        "0.001",
        "$12",
        "1,000",
        " 12",
        "12 ",
        "12\n",
        "+12",
        "1e3",
        "NaN",
        "Infinity",
        ".5",
        "12.",
        "-",
        "--1",
        "",
        "١٢",  # non-ASCII (Arabic-Indic) digits
    ],
)
def test_parse_rejects_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        Money.parse(text)


@pytest.mark.parametrize("bad", [12.34, 1234, Decimal("12.34")])
def test_parse_rejects_non_str(bad: object) -> None:
    with pytest.raises(TypeError):
        Money.parse(bad)  # type: ignore[arg-type]


# --- Display ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "$0.00"),
        (1, "$0.01"),
        (-1, "-$0.01"),
        (1234, "$12.34"),
        (123456, "$1,234.56"),
        (-123456, "-$1,234.56"),
        (100_000_000, "$1,000,000.00"),
    ],
)
def test_str(cents: int, text: str) -> None:
    assert str(Money(cents)) == text


def test_repr_shows_cents() -> None:
    assert repr(Money(-5)) == "Money(cents=-5)"


# --- Sign helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("cents", "zero", "positive", "negative"),
    [(0, True, False, False), (1, False, True, False), (-1, False, False, True)],
)
def test_sign_helpers(cents: int, zero: bool, positive: bool, negative: bool) -> None:
    money = Money(cents)
    assert money.is_zero() is zero
    assert money.is_positive() is positive
    assert money.is_negative() is negative


def test_bool_is_false_only_for_zero() -> None:
    assert not Money(0)
    assert Money(1)
    assert Money(-1)


# --- Arithmetic -------------------------------------------------------------


def test_add_and_subtract() -> None:
    assert Money(1050) + Money(250) == Money(1300)
    assert Money(1050) - Money(250) == Money(800)


def test_subtract_can_go_negative() -> None:
    assert Money(100) - Money(250) == Money(-150)


def test_sum_with_zero_start() -> None:
    assert sum([Money(1), Money(2), Money(3)], Money.zero()) == Money(6)


def test_multiply_by_int_either_side() -> None:
    assert Money(1234) * 3 == Money(3702)
    assert 3 * Money(1234) == Money(3702)
    assert Money(1234) * -1 == Money(-1234)
    assert Money(1234) * 0 == Money(0)


def test_negate_and_abs() -> None:
    assert -Money(500) == Money(-500)
    assert abs(Money(-500)) == Money(500)


@pytest.mark.parametrize("other", [1, 1.5, Decimal("1"), "1", None])
def test_add_and_subtract_reject_non_money(other: object) -> None:
    with pytest.raises(TypeError):
        Money(100) + other  # type: ignore[operator]
    with pytest.raises(TypeError):
        other + Money(100)  # type: ignore[operator]
    with pytest.raises(TypeError):
        Money(100) - other  # type: ignore[operator]


@pytest.mark.parametrize("factor", [1.5, 2.0, Decimal("2"), True, Money(2), "2"])
def test_multiply_rejects_non_int(factor: object) -> None:
    with pytest.raises(TypeError):
        Money(100) * factor  # type: ignore[operator]
    with pytest.raises(TypeError):
        factor * Money(100)  # type: ignore[operator]


def test_no_division() -> None:
    with pytest.raises(TypeError):
        Money(100) / 2  # type: ignore[operator]
    with pytest.raises(TypeError):
        Money(100) // 2  # type: ignore[operator]


# --- Comparison -------------------------------------------------------------


def test_ordering() -> None:
    assert Money(-1) < Money(0) < Money(1)
    assert Money(5) <= Money(5)
    assert Money(6) > Money(5)
    assert max(Money(-150), Money.zero()) == Money.zero()
    assert sorted([Money(3), Money(-1), Money(2)]) == [Money(-1), Money(2), Money(3)]


def test_not_equal_to_plain_numbers() -> None:
    assert Money(5) != 5
    assert Money(0) != 0


def test_ordering_against_non_money_raises() -> None:
    with pytest.raises(TypeError):
        _ = Money(5) < 5  # type: ignore[operator]


# --- Split ------------------------------------------------------------------


def test_split_leftover_goes_to_last_part() -> None:
    assert Money.parse("100.00").split(3) == (
        Money.parse("33.33"),
        Money.parse("33.33"),
        Money.parse("33.34"),
    )


def test_split_even() -> None:
    assert Money(1000).split(4) == (Money(250),) * 4


def test_split_into_one_part() -> None:
    assert Money(1234).split(1) == (Money(1234),)


def test_split_smaller_than_n_cents() -> None:
    assert Money(2).split(3) == (Money(0), Money(0), Money(2))


def test_split_zero() -> None:
    assert Money(0).split(3) == (Money(0),) * 3


def test_split_rejects_negative_amount() -> None:
    with pytest.raises(ValueError):
        Money(-100).split(2)


@pytest.mark.parametrize("n", [0, -1, 2.0, True, "2"])
def test_split_rejects_invalid_n(n: object) -> None:
    with pytest.raises(ValueError):
        Money(100).split(n)  # type: ignore[arg-type]
