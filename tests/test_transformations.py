import pytest

from transformations import calculate_net_amount, classify_order_size


def test_net_amount_applies_discount():
    assert calculate_net_amount(100.0, 10.0) == 90.0


def test_net_amount_no_discount():
    assert calculate_net_amount(250.0, 0.0) == 250.0


@pytest.mark.parametrize("amount, discount", [(-1.0, 0.0), (10.0, -5.0), (10.0, 101.0)])
def test_net_amount_rejects_invalid_input(amount, discount):
    with pytest.raises(ValueError):
        calculate_net_amount(amount, discount)


@pytest.mark.parametrize(
    "net, expected",
    [(0.0, "SMALL"), (99.99, "SMALL"), (100.0, "MEDIUM"), (999.99, "MEDIUM"), (1000.0, "LARGE")],
)
def test_classify_order_size_boundaries(net, expected):
    assert classify_order_size(net) == expected


def test_classify_order_size_rejects_negative():
    with pytest.raises(ValueError):
        classify_order_size(-0.01)
