from pydantic import BaseModel, ConfigDict, Field


class PinSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: str = Field(pattern=r"^\d{6}$")
    confirm_pin: str = Field(pattern=r"^\d{6}$")
    website: str = Field(default="", max_length=200)  # honeypot, humans leave it empty


class PinVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: str = Field(pattern=r"^\d{6}$")
    website: str = Field(default="", max_length=200)  # honeypot


class MemberProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=160)
    address: str = Field(default="", max_length=500)
    address1: str = Field(default="", max_length=500)
    postcode: str = Field(default="", pattern=r"^(\d{5})?$")
    phone: str = Field(default="", pattern=r"^([0-9+()\-\s]{8,24})?$")
    website: str = Field(default="", max_length=200)  # honeypot


class BotReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(pattern=r"^[A-Za-z0-9-]{16,64}$")
    signal: str = Field(pattern=r"^(webdriver|honeypot|headless)$")
