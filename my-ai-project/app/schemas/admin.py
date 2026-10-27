from pydantic import BaseModel, ConfigDict, Field


class GoogleSheetsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    range: str = Field(..., min_length=1, max_length=200, pattern=r"^[^\x00-\x1f]+$")
