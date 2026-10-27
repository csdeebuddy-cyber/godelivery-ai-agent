from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductImportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=300)
    category: str | None = Field(default=None, max_length=200)
    price_regular: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=200)
    highlights: list[str] = Field(default_factory=list, max_length=20)
    voice_script: str | None = Field(default=None, max_length=2000)


class PromotionImportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promo_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=300)
    applicable_products: list[str] = Field(default_factory=list, max_length=100)
    price_special: Decimal | None = Field(default=None, gt=0)
    details: str | None = Field(default=None, max_length=2000)
    free_shipping: bool | None = None
    status: str | None = Field(default=None, max_length=50)
