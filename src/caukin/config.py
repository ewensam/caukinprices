"""Supplier configuration loaded from suppliers.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "suppliers.yaml"


class Selectors(BaseModel):
    price: str | None = None
    title: str | None = "h1"


class Supplier(BaseModel):
    key: str
    name: str
    url_column: str
    prices_include_vat: bool = True
    allowed_sellers: list[str] = Field(default_factory=list)
    delay_seconds: tuple[float, float] = (3, 5)
    selectors: Selectors = Field(default_factory=Selectors)


class SuppliersFile(BaseModel):
    suppliers: list[Supplier]


def load_suppliers(path: Path = DEFAULT_PATH) -> list[Supplier]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SuppliersFile.model_validate(data).suppliers
