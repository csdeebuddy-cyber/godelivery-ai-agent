import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PageSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=160)
    body: str = Field(default="", max_length=12000)


class FAQItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=5000)


class ProductItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=3000)
    image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    regular_price: float = Field(ge=0)
    sale_price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    active: bool = True

    @model_validator(mode="after")
    def sale_price_must_not_exceed_regular_price(self) -> "ProductItem":
        if self.sale_price is not None and self.sale_price > self.regular_price:
            raise ValueError("Sale price must not exceed regular price.")
        return self


class PromotionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promotion_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    details: str = Field(min_length=1, max_length=5000)
    active: bool = True


class SiteContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: PageSection = Field(default_factory=PageSection)
    terms: PageSection = Field(default_factory=PageSection)
    security: PageSection = Field(default_factory=PageSection)
    shipping: PageSection = Field(default_factory=PageSection)
    returns: PageSection = Field(default_factory=PageSection)
    faqs: list[FAQItem] = Field(default_factory=list, max_length=100)
    products: list[ProductItem] = Field(default_factory=list, max_length=500)
    promotions: list[PromotionItem] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def item_ids_must_be_unique(self) -> "SiteContent":
        product_ids = [item.product_id.casefold() for item in self.products]
        promotion_ids = [item.promotion_id.casefold() for item in self.promotions]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Product IDs must be unique.")
        if len(set(promotion_ids)) != len(promotion_ids):
            raise ValueError("Promotion IDs must be unique.")
        serialized = json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        if len(serialized) > 900_000:
            raise ValueError("Website content exceeds the Firestore document size limit.")
        return self


class OrderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=100)


class CustomerOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=500)
    address1: str = Field(default="", max_length=500)
    postcode: str = Field(pattern=r"^\d{5}$")
    phone_number: str = Field(pattern=r"^[0-9+()\-\s]{8,24}$")
    items: list[OrderItemRequest] = Field(min_length=1, max_length=50)
    remark: str = Field(default="", max_length=1000)
    privacy_consent: bool


class MemberRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: str = Field(min_length=1, max_length=160)
    phone_number: str = Field(pattern=r"^[0-9+()\-\s]{8,24}$")
    email: str | None = Field(
        default=None,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    privacy_consent: bool
