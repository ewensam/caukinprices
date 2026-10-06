"""Supplier configuration loaded from suppliers.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

def project_file(*parts: str) -> Path:
    """Locate a repo data file (suppliers.yaml, data/...). These live in the checkout, not
    the installed package, so look in the working directory first, then the source tree."""
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (p := base.joinpath(*parts)).exists():
            return p
    raise FileNotFoundError(f"{Path(*parts)} not found - run caukin from the project folder")


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


def load_suppliers(path: Path | None = None) -> list[Supplier]:
    path = path or project_file("suppliers.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SuppliersFile.model_validate(data).suppliers
