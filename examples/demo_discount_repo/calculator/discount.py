"""Discount calculation utility."""


def calculate_discount(price: float, discount: float) -> float:
    """
    Calculate the discounted price given a base price and a discount.

    Bug: Assumes discount is always a decimal (e.g. 0.20) rather than a percentage (e.g. 20).
    When 20 is passed for a 20% discount, it returns a negative or incorrect price.
    """
    return price - (price * discount)

