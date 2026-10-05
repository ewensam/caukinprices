"""Price normalisation: inc-VAT pack price -> ex-VAT price per canonical unit."""


def ex_vat(price: float, vat_rate: float, includes_vat: bool = True) -> float:
    return price / (1 + vat_rate) if includes_vat else price


def unit_price(price_ex_vat: float, pack_qty: float) -> float:
    if pack_qty <= 0:
        raise ValueError("pack_qty must be > 0")
    return price_ex_vat / pack_qty
