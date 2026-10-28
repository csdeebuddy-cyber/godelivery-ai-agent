from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImageLinkImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2000)


class GoogleSheetsProductColumns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(default=1, ge=1, le=100)
    product_name: int = Field(default=2, ge=1, le=100)
    regular_price: int = Field(default=3, ge=1, le=100)
    selling_price: int = Field(default=4, ge=1, le=100)
    stock_quantity: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def columns_must_be_unique(self) -> "GoogleSheetsProductColumns":
        columns = list(self.model_dump().values())
        if len(set(columns)) != len(columns):
            raise ValueError("Each product field must use a different column position.")
        return self


class GoogleSheetsPromotionColumns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promotion_id: int = Field(default=1, ge=1, le=100)
    promotion_name: int = Field(default=2, ge=1, le=100)
    conditions: int = Field(default=3, ge=1, le=100)

    @model_validator(mode="after")
    def columns_must_be_unique(self) -> "GoogleSheetsPromotionColumns":
        columns = list(self.model_dump().values())
        if len(set(columns)) != len(columns):
            raise ValueError("Each promotion field must use a different column position.")
        return self


class GoogleSheetsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    range: str = Field(..., min_length=1, max_length=200, pattern=r"^[^\x00-\x1f]+$")
    product_columns: GoogleSheetsProductColumns = Field(
        default_factory=GoogleSheetsProductColumns
    )
    promotion_range: str = Field(
        default="promotion!A2:C",
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f]+$",
    )
    promotion_columns: GoogleSheetsPromotionColumns = Field(
        default_factory=GoogleSheetsPromotionColumns
    )
    orders_range: str = Field(
        default="orders!A:O",
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f]+$",
    )
    member_range: str = Field(
        default="MEMBER!A:F",
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f]+$",
    )
