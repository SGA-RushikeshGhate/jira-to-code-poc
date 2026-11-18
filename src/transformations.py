"""Pure business logic for the sample ETL.

Kept free of Spark so it can be unit-tested anywhere (locally, in CI, in the agent sandbox).
"""


def calculate_net_amount(amount: float, discount_pct: float) -> float:
    """Return the order amount after applying a percentage discount (0-100)."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")
    return round(amount * (1 - discount_pct / 100), 2)
