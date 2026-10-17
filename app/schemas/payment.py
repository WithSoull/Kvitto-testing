from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.domain.enums import PaymentMethod, PaymentStatus
from app.domain.promo import normalize_promo_code


class PaymentCreate(BaseModel):
    # extra="forbid": a misspelled field (e.g. "promocode") is a 422, not a silently full price.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    tariff_id: str = Field(min_length=1, max_length=32, examples=["standard"])
    email: EmailStr = Field(examples=["user@example.com"])
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = Field(
        default=None, description="Required for installment, forbidden otherwise"
    )
    promo_code: str | None = Field(default=None, max_length=32, examples=["KVITTO10"])

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, email: str) -> str:
        return email.lower()

    @field_validator("promo_code")
    @classmethod
    def normalize_promo(cls, promo_code: str | None) -> str | None:
        return normalize_promo_code(promo_code)

    @model_validator(mode="after")
    def check_installment_months(self) -> Self:
        if self.method is PaymentMethod.INSTALLMENT and self.installment_months is None:
            raise ValueError("installment_months is required for installment")
        if self.method is not PaymentMethod.INSTALLMENT and self.installment_months is not None:
            raise ValueError("installment_months is allowed only for installment")
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: PaymentStatus
    tariff_id: str
    amount: int = Field(description="Amount to pay in kopecks")
    discount: int = Field(description="Discount in kopecks")
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None = Field(description="Installment payments in kopecks")
    email: str
    created_at: datetime
