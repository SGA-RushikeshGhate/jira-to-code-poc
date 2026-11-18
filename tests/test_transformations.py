import pytest

from transformations import calculate_net_amount


def test_net_amount_applies_discount():
    assert calculate_net_amount(100.0, 10.0) == 90.0


def test_net_amount_no_discount():
    assert calculate_net_amount(250.0, 0.0) == 250.0


@pytest.mark.parametrize("amount, discount", [(-1.0, 0.0), (10.0, -5.0), (10.0, 101.0)])
def test_net_amount_rejects_invalid_input(amount, discount):
    with pytest.raises(ValueError):
        calculate_net_amount(amount, discount)
