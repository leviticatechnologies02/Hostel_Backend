from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.hostel import Hostel
    from app.models.payment import Payment
    from app.models.room import Bed, Room
    from app.models.student import Student
    from app.models.user import User


class BookingMode(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class BookingStatus(str, enum.Enum):
    DRAFT = "draft"
    PAYMENT_PENDING = "payment_pending"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BedStayStatus(str, enum.Enum):
    RESERVED = "reserved"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WaitlistStatus(str, enum.Enum):
    ACTIVE = "active"
    NOTIFIED = "notified"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


class CheckoutRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Booking(BaseModel):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("check_out_date > check_in_date", name="ck_booking_dates"),
    )

    booking_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    visitor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    hostel_id: Mapped[str] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    bed_id: Mapped[str | None] = mapped_column(
        ForeignKey("beds.id", ondelete="CASCADE"), nullable=True, index=True
    )
    booking_mode: Mapped[BookingMode] = mapped_column(Enum(BookingMode), index=True)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), index=True)
    check_in_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_hours: Mapped[int | None] = mapped_column(nullable=True)
    total_nights: Mapped[int | None] = mapped_column(nullable=True)
    total_months: Mapped[int | None] = mapped_column(nullable=True)
    base_rent_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    security_deposit: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    booking_advance: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(10, 2))
    full_name: Mapped[str] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    id_document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    guardian_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    special_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    visitor: Mapped[User] = relationship("User", foreign_keys=[visitor_id])
    hostel: Mapped[Hostel] = relationship("Hostel")
    room: Mapped[Room] = relationship("Room")
    bed: Mapped[Bed | None] = relationship("Bed", foreign_keys=[bed_id])
    status_history: Mapped[list[BookingStatusHistory]] = relationship(
        "BookingStatusHistory", back_populates="booking", cascade="all, delete-orphan"
    )
    bed_stays: Mapped[list[BedStay]] = relationship(
        "BedStay", back_populates="booking"
    )
    payments: Mapped[list[Payment]] = relationship("Payment", back_populates="booking")


class BookingStatusHistory(BaseModel):
    __tablename__ = "booking_status_history"

    booking_id: Mapped[str] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[BookingStatus | None] = mapped_column(
        Enum(BookingStatus), nullable=True
    )
    new_status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus))
    changed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped[Booking] = relationship("Booking", back_populates="status_history")


class CheckoutRequest(BaseModel):
    """A user-initiated checkout that must be reviewed by a hostel admin."""

    __tablename__ = "checkout_requests"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_checkout_request_booking"),
    )

    booking_id: Mapped[str] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    hostel_id: Mapped[str] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=CheckoutRequestStatus.PENDING.value, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    booking: Mapped[Booking] = relationship("Booking")


class BedStay(BaseModel):
    """Source of truth for bed occupancy. Overlap prevention enforced in service layer."""

    __tablename__ = "bed_stays"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_bed_stay_dates"),
    )

    hostel_id: Mapped[str] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    bed_id: Mapped[str] = mapped_column(
        ForeignKey("beds.id", ondelete="CASCADE"), index=True
    )
    booking_id: Mapped[str | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=True, index=True
    )
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BedStayStatus] = mapped_column(Enum(BedStayStatus), index=True)

    booking: Mapped[Booking | None] = relationship("Booking", back_populates="bed_stays")
    bed: Mapped[Bed] = relationship("Bed", back_populates="bed_stays")
    student: Mapped[Student | None] = relationship("Student", back_populates="bed_stays")


class Inquiry(BaseModel):
    __tablename__ = "inquiries"

    hostel_id: Mapped[str] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)



class WaitlistEntry(BaseModel):
    __tablename__ = "waitlist_entries"

    visitor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    hostel_id: Mapped[str] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    bed_id: Mapped[str | None] = mapped_column(ForeignKey("beds.id", ondelete="CASCADE"), nullable=True, index=True)
    check_in_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    booking_mode: Mapped[BookingMode] = mapped_column(Enum(BookingMode), index=True)
    status: Mapped[WaitlistStatus] = mapped_column(Enum(WaitlistStatus), index=True, default=WaitlistStatus.ACTIVE)
    notified_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Add these relationships if missing
    visitor: Mapped["User"] = relationship("User", foreign_keys=[visitor_id])
    hostel: Mapped["Hostel"] = relationship("Hostel")
    room: Mapped["Room"] = relationship("Room")
    bed: Mapped["Bed | None"] = relationship("Bed")
