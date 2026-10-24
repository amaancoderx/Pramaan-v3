import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

UPI_ID_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63}$")
Strictness = Literal["lenient", "standard", "strict"]


def _check_upi(v: str) -> str:
    v = v.strip().lower()
    if not UPI_ID_RE.match(v):
        raise ValueError("Enter a valid UPI ID, e.g. shopname@okhdfcbank")
    return v


class MerchantRegister(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=80)
    registered_upi_id: str
    registered_receiver_name: Optional[str] = Field(default=None, min_length=2, max_length=100)

    @field_validator("registered_receiver_name")
    @classmethod
    def _receiver_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Enter the receiver/account name exactly as shown in the payment app")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("registered_upi_id")
    @classmethod
    def _upi(cls, v: str) -> str:
        return _check_upi(v)


class MerchantLogin(BaseModel):
    email: str
    password: str


class MerchantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    registered_upi_id: Optional[str] = None
    registered_receiver_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    allowed_window_minutes: Optional[int] = Field(default=None, ge=5, le=10080)
    strictness: Optional[Strictness] = None

    @field_validator("registered_upi_id")
    @classmethod
    def _upi(cls, v: Optional[str]) -> Optional[str]:
        return _check_upi(v) if v is not None else v

    @field_validator("registered_receiver_name")
    @classmethod
    def _receiver_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Enter the receiver/account name exactly as shown in the payment app")
        return v


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    registered_upi_id: str
    registered_receiver_name: Optional[str] = None
    allowed_window_minutes: int
    strictness: str
    api_key: Optional[str] = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    merchant: MerchantResponse
