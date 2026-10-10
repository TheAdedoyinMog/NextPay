"""Upper bounds the API puts on what a user can enter.

The engine has no upper limits; these exist so that no request can overflow a
database column or store an absurd value. They are API limits, not money rules.
"""

# Matches the String(100) name columns.
MAX_NAME_LENGTH = 100

# $1 billion, far inside BIGINT.
MAX_CENTS = 100_000_000_000

MAX_PRIORITY = 1_000

# Ten years between occurrences of a bill.
MAX_REPEAT_EVERY_MONTHS = 120

# 1,000% a year, in basis points.
MAX_APR_BPS = 100_000

# How many balance snapshots one request may list.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
