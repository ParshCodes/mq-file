from decimal import Decimal, ROUND_HALF_UP


def test_tax_uses_currency_half_up_rounding():
    subtotal = Decimal("50.00")
    tax = (subtotal * Decimal("0.0825")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert tax == Decimal("4.13")
    assert subtotal + tax == Decimal("54.13")
