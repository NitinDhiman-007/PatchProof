# Demo Discount Repository

A deterministic sample Python repository used to demonstrate PatchProof's automated reproduction, patch generation, and evidence verification workflow.

## Bug Scenario

The function `calculate_discount(price, discount)` in `calculator/discount.py` computes discounts:

```python
def calculate_discount(price: float, discount: float) -> float:
    return price - (price * discount)
```

### Observed Defect
When users pass a percentage value (e.g., `20` for a 20% discount on a 1000 item), the function calculates:
`1000 - (1000 * 20) = -19000` instead of `800.0`.

### Expected Behavior
`calculate_discount(1000, 20) == 800.0`

