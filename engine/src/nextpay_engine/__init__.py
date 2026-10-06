"""NextPay planning engine.

Pure and deterministic: no database, no network, no clock. The same inputs
always produce the same plan. See docs/adr/0002-engine-as-separate-package.md.
"""

from nextpay_engine.money import Money

ENGINE_VERSION = "0.1.0"

__all__ = ["ENGINE_VERSION", "Money"]
