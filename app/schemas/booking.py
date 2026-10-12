from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.base import TimestampedResponse
from typing import Optional
from enum import Enum
from sqlalchemy import func


class BookingModeEnum(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class BookingCreateRequest(BaseModel):
    hostel_id: str
    room_id: str
    bed_id: Optional[str] = None  # Can be assigned later during approval
    booking_mode: BookingModeEnum
    check_in_date: datetime
    check_out_date: datetime
    full_name: str = Field(min_length=2, max_length=255, pattern=r"^[A-Za-z\s\-\']+$")
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    occupation: Optional[str] = Field(None, max_length=255)
    institution: Optional[str] = Field(None, max_length=255)
    current_address: Optional[str] = None
    id_type: Optional[str] = Field(None, max_length=100)
    id_document_url: Optional[str] = Field(None, max_length=500)
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=30)
    emergency_contact_relationship: Optional[str] = Field(None, max_length=100)
    guardian_name: Optional[str] = Field(None, max_length=255)
    guardian_phone: Optional[str] = Field(None, max_length=30)
    special_requirements: Optional[str] = None
    base_rent_amount: float = Field(ge=0, default=0)
    security_deposit: float = Field(ge=0, default=0)
    booking_advance: float = Field(ge=0, default=0)
    grand_total: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def validate_dates_and_totals(self) -> "BookingCreateRequest":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if self.grand_total == 0:
            self.grand_total = self.base_rent_amount + self.security_deposit
        return self
    
    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalized = v.lower()
        if normalized in ["m", "male"]:
            return "M"
        if normalized in ["f", "female"]:
            return "F"
        if normalized in ["other"]:
            return "Other"
        raise ValueError("Gender must be 'M', 'F', or 'Other'")


class BookingResponse(TimestampedResponse):
    id: str
    booking_number: str
    visitor_id: str
    status: str
    booking_mode: str
    hostel_id: str
    room_id: str
    bed_id: str | None = None
    check_in_date: datetime
    check_out_date: datetime
    total_hours: int | None = None
    total_nights: int | None = None
    total_months: int | None = None
    base_rent_amount: float
    security_deposit: float
    booking_advance: float
    grand_total: float
    full_name: str
    id_type: str | None = None
    id_document_url: str | None = None
    rejection_reason: str | None = None
    cancellation_reason: str | None = None
    approved_by: str | None = None


class BookingListResponse(BookingResponse):
    """Booking card data with its hostel, room and bed display details."""

    hostel_name: str | None = None
    hostel_address: str | None = None
    hostel_city: str | None = None
    hostel_state: str | None = None
    hostel_pincode: str | None = None
    room_number: str | None = None
    room_type: str | None = None
    room_floor: int | None = None
    bed_number: str | None = None


class BookingInitiateRequest(BaseModel):
    hostel_id: str
    room_id: str
    bed_id: str | None = None
    booking_mode: BookingModeEnum
    check_in_date: datetime
    check_out_date: datetime
    base_rent_amount: float = Field(ge=0)
    security_deposit: float = Field(ge=0, default=0)
    booking_advance: float = Field(ge=0, default=0)
    grand_total: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def validate_dates_and_totals(self) -> "BookingInitiateRequest":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if self.grand_total == 0:
            self.grand_total = self.base_rent_amount + self.security_deposit
        return self


class BookingInitiateResponse(BaseModel):
    booking_id: str
    booking_number: str
    status: str
    pricing: dict


class BookingApplicantPatchRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    occupation: Optional[str] = Field(None, max_length=255)
    institution: Optional[str] = Field(None, max_length=255)
    current_address: Optional[str] = None
    id_type: Optional[str] = Field(None, max_length=100)
    id_document_url: Optional[str] = Field(None, max_length=500)   # ← was missing — caused 500
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=30)
    emergency_contact_relationship: Optional[str] = Field(None, max_length=100)
    guardian_name: Optional[str] = Field(None, max_length=255)
    guardian_phone: Optional[str] = Field(None, max_length=30)
    special_requirements: Optional[str] = None


class BookingApprovalRequest(BaseModel):
    bed_id: str
    

class BookingRejectionRequest(BaseModel):
    reason: Optional[str] = None


class BookingCancellationRequest(BaseModel):
    reason: Optional[str] = None


class CheckoutRequestCreate(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class CheckoutRequestReview(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class CheckoutRequestResponse(TimestampedResponse):
    booking_id: str
    hostel_id: str
    requested_by: str
    status: str
    reason: str | None = None
    reviewed_by: str | None = None
    admin_note: str | None = None
    reviewed_at: datetime | None = None


class BookingStatusHistoryResponse(TimestampedResponse):
    booking_id: str
    old_status: str | None
    new_status: str
    changed_by: str | None
    note: str | None

class WaitlistJoinRequest(BaseModel):
    hostel_id: str
    room_id: str
    bed_id: str | None = None
    booking_mode: BookingModeEnum
    check_in_date: datetime
    check_out_date: datetime
    
    @model_validator(mode="after")
    def validate_dates(self) -> "WaitlistJoinRequest":
        from datetime import datetime as datetime_type
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if self.check_in_date.date() < datetime_type.today().date():
            raise ValueError("check_in_date cannot be in the past")
        return self

class WaitlistEntryResponse(TimestampedResponse):
    id: str
    visitor_id: str
    hostel_id: str
    room_id: str
    bed_id: str | None = None
    booking_mode: str
    check_in_date: datetime
    check_out_date: datetime
    status: str
    position: int
