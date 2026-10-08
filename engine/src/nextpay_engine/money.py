"""The Money value object: an exact, immutable amount of integer cents.

All money arithmetic, rounding, and splitting in NextPay lives here
(see docs/adr/0001-money-as-integer-cents.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self

# Optional minus, ASCII digits, then optionally a point and one or two digits.
_DECIMAL_PATTERN = re.compile(r"(-?)([0-9]+)(?:\.([0-9]{1,2}))?", re.ASCII)


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """An exact amount of money, stored as integer cents.

    ``Money(1234)`` is $12.34. Only a plain ``int`` is accepted: floats, Decimals,
    and bools raise ``TypeError``, so imprecise values can never enter the engine.

    Amounts are signed. A negative amount is a deficit, for example a shortfall
    when reserves exceed available funds. Money never clamps at zero on its own;
    rules such as "a bill amount must be positive" belong to the domain types that
    hold Money, and flooring is written explicitly as ``max(x, Money.zero())``.
    """

    cents: int

    def __post_init__(self) -> None:
        # bool is a subclass of int, so isinstance() would let Money(True) through.
        if type(self.cents) is not int:
            raise TypeError(f"Money cents must be an int, got {type(self.cents).__name__}")

    @classmethod
    def zero(cls) -> Self:
        """Return $0.00. Useful as the start value for ``sum()``."""
        return cls(0)

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse a plain decimal string such as ``"12.34"`` or ``"-0.5"``.

        Accepted: an optional leading minus, one or more ASCII digits, and an
        optional point followed by one or two digits. Everything else raises
        ``ValueError``: currency symbols, thousands separators, whitespace, a
        leading plus, exponents, ``"NaN"``, ``".5"``, ``"12."``, and more than two
        decimal places. Parsing never rounds.
        """
        if not isinstance(text, str):
            raise TypeError(f"Money.parse expects a str, got {type(text).__name__}")
        match = _DECIMAL_PATTERN.fullmatch(text)
        if match is None:
            raise ValueError(f"not a valid money amount: {text!r}")
        sign, whole, fraction = match.groups()
        cents = int(whole) * 100 + int((fraction or "").ljust(2, "0"))
        return cls(-cents if sign else cents)

    def is_zero(self) -> bool:
        return self.cents == 0

    def is_positive(self) -> bool:
        return self.cents > 0

    def is_negative(self) -> bool:
        return self.cents < 0

    # Arithmetic is closed over Money, except multiplication by a plain int.
    # Anything else returns NotImplemented, so Python raises TypeError. There is
    # deliberately no division operator: dividing needs a rounding rule, so use split().

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents - other.cents)

    def __mul__(self, factor: int) -> Money:
        if type(factor) is not int:
            return NotImplemented
        return Money(self.cents * factor)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.cents)

    def __abs__(self) -> Money:
        return Money(abs(self.cents))

    def __bool__(self) -> bool:
        """Like int: $0.00 is falsy. Prefer ``is_zero()`` for clarity."""
        return self.cents != 0

    def split(self, n: int) -> tuple[Money, ...]:
        """Divide into ``n`` parts that sum exactly to this amount.

        Every part gets the same whole number of cents; the leftover cents all go
        to the last part, so ``Money.parse("100").split(3)`` is $33.33, $33.33,
        $33.34. An amount smaller than ``n`` cents yields leading zero parts.

        Raises ``ValueError`` if the amount is negative or ``n`` is not an int >= 1.
        """
        if type(n) is not int or n < 1:
            raise ValueError(f"split needs an int n >= 1, got {n!r}")
        if self.cents < 0:
            raise ValueError(f"cannot split a negative amount: {self}")
        share, leftover = divmod(self.cents, n)
        return (Money(share),) * (n - 1) + (Money(share + leftover),)

    def prorate(self, part: int, whole: int) -> Money:
        """This amount scaled by ``part / whole``, rounded up to the next cent.

        Rounding up means a prorated need is never underfunded; the overshoot is
        under one cent. ``Money(20000).prorate(10, 14)`` is $142.86.

        Raises ``ValueError`` if the amount is negative, ``part`` is not an int >= 0,
        or ``whole`` is not an int >= 1.
        """
        if type(part) is not int or part < 0:
            raise ValueError(f"prorate needs an int part >= 0, got {part!r}")
        if type(whole) is not int or whole < 1:
            raise ValueError(f"prorate needs an int whole >= 1, got {whole!r}")
        if self.cents < 0:
            raise ValueError(f"cannot prorate a negative amount: {self}")
        return Money(-(-self.cents * part // whole))  # ceiling division

    def __str__(self) -> str:
        """Format for tests and debugging, e.g. ``-$1,234.56``. The app formats its own."""
        sign = "-" if self.cents < 0 else ""
        dollars, cents = divmod(abs(self.cents), 100)
        return f"{sign}${dollars:,}.{cents:02d}"
