"""
StudentService — creates tenant records for qualifying long-stay bookings.
"""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingMode, BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.student_repository import StudentRepository


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.booking_repository = BookingRepository(session)
        self.student_repository = StudentRepository(session)

    @staticmethod
    def is_tenant_booking(booking: Booking) -> bool:
        """Monthly and stays longer than ten daily nights are tenant stays."""
        if booking.booking_mode == BookingMode.MONTHLY:
            return True
        if booking.booking_mode != BookingMode.DAILY:
            return False

        total_nights = booking.total_nights
        if total_nights is None:
            total_nights = max(1, (booking.check_out_date - booking.check_in_date).days)
        return total_nights > 10

    async def ensure_tenant_record_from_booking(
        self, *, booking_id: str, actor_id: str, commit: bool = True
    ):
        """Create the tenant profile for a qualifying approved or checked-in stay.

        This is idempotent so it can be used by approval, check-in, and repair flows.
        """
        booking = await self.booking_repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status not in (BookingStatus.APPROVED, BookingStatus.CHECKED_IN):
            raise HTTPException(
                status_code=400,
                detail=f"Booking must be APPROVED or CHECKED_IN to create tenant record. Current: {booking.status.value}",
            )

        if not self.is_tenant_booking(booking):
            raise HTTPException(
                status_code=400,
                detail="Only monthly or daily stays longer than 10 nights create a tenant record.",
            )

        if booking.bed_id is None:
            raise HTTPException(status_code=400, detail="Booking has no allocated bed.")

        existing = await self.student_repository.get_student_by_booking(str(booking.id))
        if existing is not None:
            return existing

        # Create student record
        student = await self.student_repository.create_from_booking(booking=booking)

        # A reservation becomes occupied only at physical check-in.
        if booking.status == BookingStatus.CHECKED_IN:
            await self.student_repository.activate_bed_stay(str(booking.id), str(student.id))
        else:
            await self.student_repository.link_bed_stay_to_student(str(booking.id), str(student.id))

        # Promote user role to student
        await self.student_repository.promote_user_to_student(str(booking.visitor_id))

        # ✨ REVOKE ALL EXISTING TOKENS - Force re-login
        from app.repositories.user_repository import UserRepository
        from datetime import UTC, datetime
        
        repo = UserRepository(self.session)
        await repo.revoke_all_refresh_tokens(
            user_id=str(booking.visitor_id),
            revoked_at=datetime.now(UTC)
        )
        if commit:
            await self.session.commit()
        
        await self.session.refresh(student)
        return student

    async def check_in_from_booking(self, *, booking_id: str, actor_id: str):
        """Create a tenant record from a checked-in qualifying booking."""
        return await self.ensure_tenant_record_from_booking(
            booking_id=booking_id,
            actor_id=actor_id,
        )
