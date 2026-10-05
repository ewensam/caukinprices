import pytest

from caukin.pricing import ex_vat, unit_price


def test_ex_vat():
    assert ex_vat(12.0, 0.2) == pytest.approx(10.0)
    assert ex_vat(12.0, 0.2, includes_vat=False) == 12.0


def test_unit_price_timber_per_metre():
    # 2.4m length at £6.75 inc VAT -> £5.625 ex VAT -> £2.34375/m
    assert unit_price(ex_vat(6.75, 0.2), 2.4) == pytest.approx(2.34375)


def test_unit_price_rejects_zero_pack():
    with pytest.raises(ValueError):
        unit_price(10, 0)
